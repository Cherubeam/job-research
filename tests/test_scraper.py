"""Tests for scraper.py"""

import json

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams
from job_research.sources import Backend, catalog
from job_research.scraper import ClaudeScraper


def _make_text_response(text: str, search_urls: list[str] | None = None) -> MagicMock:
    """Build a mock API response containing text and optional web_search_tool_result blocks."""
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = text
    blocks = [text_block]

    if search_urls:
        search_results = []
        for url in search_urls:
            result = MagicMock()
            result.type = "web_search_result"
            result.url = url
            result.title = "Mock result"
            search_results.append(result)
        search_block = MagicMock()
        search_block.type = "web_search_tool_result"
        search_block.content = search_results
        blocks.insert(0, search_block)

    response = MagicMock()
    response.content = blocks
    return response


INDEED = (catalog.get("indeed"),)


@pytest.fixture
def scraper() -> ClaudeScraper:
    with patch("job_research.scraper.anthropic.Anthropic"):
        return ClaudeScraper(api_key="sk-test", model="claude-haiku-4-5-20251001", max_jobs=10)


# --------------------------------------------------------- Pydantic JobListing


class TestJobListingModel:
    def test_rejects_empty_title(self):
        with pytest.raises(ValidationError, match="title must not be empty"):
            JobListing(title="", company="Co", location="Berlin")

    def test_rejects_whitespace_title(self):
        with pytest.raises(ValidationError, match="title must not be empty"):
            JobListing(title="   ", company="Co", location="Berlin")

    def test_rejects_missing_title(self):
        with pytest.raises(ValidationError):
            JobListing(company="Co", location="Berlin")  # type: ignore[call-arg]

    def test_coerces_string_salary(self):
        listing = JobListing(title="Eng", salary_min="€70.000", salary_max="90k")  # type: ignore[arg-type]
        assert listing.salary_min == 70000
        assert listing.salary_max == 90000

    def test_accepts_null_salary(self):
        listing = JobListing(title="Eng", salary_min=None, salary_max=None)
        assert listing.salary_min is None
        assert listing.salary_max is None

    def test_accepts_int_salary(self):
        listing = JobListing(title="Eng", salary_min=80000, salary_max=120000)
        assert listing.salary_min == 80000
        assert listing.salary_max == 120000

    def test_defaults(self):
        listing = JobListing(title="Eng")
        assert listing.company == ""
        assert listing.location == ""
        assert listing.salary_min is None
        assert listing.salary_max is None
        assert listing.salary_currency == "EUR"
        assert listing.job_board == ""
        assert listing.job_url == ""
        assert listing.work_type == ""
        assert listing.description == ""
        assert listing.posted_date is None

    def test_salary_midpoint(self):
        listing = JobListing(title="Eng", salary_min=80000, salary_max=120000)
        assert listing.salary_midpoint() == 100000.0

    def test_salary_midpoint_none(self):
        listing = JobListing(title="Eng")
        assert listing.salary_midpoint() is None


# ----------------------------------------------------------------- salary norm


@pytest.mark.parametrize(
    "salary_str_min,salary_str_max,expected_min,expected_max",
    [
        ("€80.000", "120.000", 80000, 120000),
        ("70k", "100k", 70000, 100000),
        ("ab 80000 EUR", None, 80000, None),
    ],
)
def test_salary_coercion_from_strings(salary_str_min, salary_str_max, expected_min, expected_max):
    listing = JobListing(
        title="Eng",
        salary_min=salary_str_min,  # type: ignore[arg-type]
        salary_max=salary_str_max,  # type: ignore[arg-type]
    )
    assert listing.salary_min == expected_min
    assert listing.salary_max == expected_max


# --------------------------------------------------------------- deduplication


def test_build_search_query_contains_keywords(scraper, sample_job_search_params):
    query = scraper._build_search_query(sample_job_search_params)
    assert "AI Engineer" in query
    assert "Berlin" in query


def test_build_search_query_excludes_site_clause(scraper, sample_job_search_params):
    query = scraper._build_search_query(sample_job_search_params)
    assert "site:" not in query


def test_build_system_prompt_contains_max_jobs(scraper):
    prompt = scraper._build_system_prompt(INDEED)
    assert "up to 10)" in prompt


def test_build_system_prompt_contains_anti_fabrication_rule(scraper):
    prompt = scraper._build_system_prompt(INDEED)
    assert "copied verbatim from a web_search result" in prompt


def test_build_system_prompt_contains_expired_listing_rule(scraper):
    prompt = scraper._build_system_prompt(INDEED)
    assert "expired" in prompt
    assert "abgelaufen" in prompt


def test_default_selection_resolves_to_the_registry_defaults():
    sources = catalog.resolve(JobSearchParams().enabled_sources, Backend.CLAUDE)
    assert {s.id for s in sources} == {"indeed", "arbeitsagentur"}


def test_explicit_selection_is_honoured():
    params = JobSearchParams(enabled_sources=["stepstone", "indeed"])
    sources = catalog.resolve(params.enabled_sources, Backend.CLAUDE)
    assert {s.id for s in sources} == {"stepstone", "indeed"}


def test_search_jobs_rejects_a_selection_this_backend_cannot_reach(scraper, tmp_cache_dir):
    """Selecting nothing reachable must fail loudly, not silently search nothing."""
    params = JobSearchParams(enabled_sources=[])
    with pytest.raises(RuntimeError, match="No sources selected"):
        scraper.search_jobs(params, tmp_cache_dir)


# ---------------------------------------------------------- API call (mocked)


def test_make_api_call_retries_on_server_error(scraper):
    """Non-429 APIStatusError uses short exponential backoff."""
    import anthropic as anthropic_module

    mock_client = MagicMock()
    scraper._client = mock_client

    error = anthropic_module.APIStatusError(
        "server error", response=MagicMock(status_code=500), body={}
    )
    success_response = MagicMock()
    success_response.content = []
    mock_client.messages.create.side_effect = [error, success_response]

    with patch("job_research.scraper.time.sleep") as mock_sleep:
        result = scraper._make_api_call([{"role": "user", "content": "test"}])

    assert mock_client.messages.create.call_count == 2
    assert result is success_response
    # First attempt backoff: 2**0 = 1s
    mock_sleep.assert_any_call(1)


def test_make_api_call_rate_limit_uses_retry_after_header(scraper):
    """429 RateLimitError reads retry-after header for sleep duration."""
    import anthropic as anthropic_module

    mock_client = MagicMock()
    scraper._client = mock_client

    response_mock = MagicMock(status_code=429)
    response_mock.headers = {"retry-after": "30"}
    error = anthropic_module.RateLimitError("rate limited", response=response_mock, body={})
    success_response = MagicMock()
    success_response.content = []
    mock_client.messages.create.side_effect = [error, success_response]

    with patch("job_research.scraper.time.sleep") as mock_sleep:
        result = scraper._make_api_call([{"role": "user", "content": "test"}])

    assert mock_client.messages.create.call_count == 2
    assert result is success_response
    mock_sleep.assert_any_call(30)


def test_make_api_call_rate_limit_defaults_to_60s(scraper):
    """429 without retry-after header defaults to 60s sleep."""
    import anthropic as anthropic_module

    mock_client = MagicMock()
    scraper._client = mock_client

    response_mock = MagicMock(status_code=429)
    response_mock.headers = {}
    error = anthropic_module.RateLimitError("rate limited", response=response_mock, body={})
    success_response = MagicMock()
    success_response.content = []
    mock_client.messages.create.side_effect = [error, success_response]

    with patch("job_research.scraper.time.sleep") as mock_sleep:
        result = scraper._make_api_call([{"role": "user", "content": "test"}])

    assert mock_client.messages.create.call_count == 2
    assert result is success_response
    mock_sleep.assert_any_call(60)


def test_client_created_with_max_retries_zero():
    """Anthropic client is initialized with max_retries=0 to disable SDK retries."""
    with patch("job_research.scraper.anthropic.Anthropic") as mock_anthropic:
        ClaudeScraper(api_key="sk-test", model="claude-haiku-4-5-20251001")
    mock_anthropic.assert_called_once_with(api_key="sk-test", max_retries=0)


def test_search_jobs_raises_on_exception(scraper, sample_job_search_params, tmp_cache_dir):
    scraper._client.messages.create = MagicMock(side_effect=Exception("boom"))
    with pytest.raises(Exception, match="boom"):
        scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


# -------------------------------------------------- _search_and_extract tests


class TestSearchAndExtract:
    def test_returns_listings_matching_search_urls(self, scraper):
        jobs = [
            {
                "title": "AI Engineer",
                "company": "TechCo",
                "location": "Berlin",
                "salary_min": 80000,
                "salary_max": 120000,
                "work_type": "Remote",
                "job_board": "Indeed",
                "job_url": "https://de.indeed.com/viewjob?jk=abc123",
            },
        ]
        scraper._client.messages.create.return_value = _make_text_response(
            json.dumps(jobs),
            search_urls=["https://de.indeed.com/viewjob?jk=abc123"],
        )
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert total == 1
        assert listings[0].title == "AI Engineer"

    def test_filters_fabricated_urls(self, scraper):
        """Listings with URLs not in search results are discarded."""
        jobs = [
            {
                "title": "Real Job",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=real123",
            },
            {
                "title": "Fake Job",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=fabricated",
            },
        ]
        scraper._client.messages.create.return_value = _make_text_response(
            json.dumps(jobs),
            search_urls=["https://de.indeed.com/viewjob?jk=real123"],
        )
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert listings[0].title == "Real Job"
        assert total == 2

    def test_raises_on_no_text(self, scraper):
        response = MagicMock()
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        response.content = [tool_block]
        scraper._client.messages.create.return_value = response
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="no text content"):
                scraper._search_and_extract("test query", INDEED)

    def test_raises_on_empty_text(self, scraper):
        scraper._client.messages.create.return_value = _make_text_response("   ")
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="no text content"):
                scraper._search_and_extract("test query", INDEED)

    def test_raises_on_invalid_json_after_retry(self, scraper):
        """Both initial response and follow-up retry return non-JSON text."""
        scraper._client.messages.create.side_effect = [
            _make_text_response("not json at all"),
            _make_text_response("still not json"),
        ]
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
                scraper._search_and_extract("test query", INDEED)

    def test_raises_on_non_array(self, scraper):
        scraper._client.messages.create.side_effect = [
            _make_text_response('{"not": "array"}'),
            _make_text_response('{"still": "not array"}'),
        ]
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
                scraper._search_and_extract("test query", INDEED)

    def test_strips_markdown_fences(self, scraper):
        jobs = [
            {
                "title": "ML Eng",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=fence1",
            }
        ]
        fenced = f"```json\n{json.dumps(jobs)}\n```"
        scraper._client.messages.create.return_value = _make_text_response(
            fenced,
            search_urls=["https://de.indeed.com/viewjob?jk=fence1"],
        )
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert listings[0].title == "ML Eng"

    def test_skips_invalid_items(self, scraper):
        items = [
            {
                "title": "Valid Job",
                "company": "Co",
                "job_url": "https://de.indeed.com/viewjob?jk=valid",
            },
            {"company": "No Title"},  # missing title → ValidationError
            {"title": "", "company": "Empty Title"},  # empty title → ValidationError
        ]
        scraper._client.messages.create.return_value = _make_text_response(
            json.dumps(items),
            search_urls=["https://de.indeed.com/viewjob?jk=valid"],
        )
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert total == 3
        assert listings[0].title == "Valid Job"

    def test_narrative_response_triggers_followup(self, scraper):
        """When initial response is narrative, a follow-up call extracts JSON."""
        jobs = [
            {
                "title": "AI Eng",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=narr1",
            }
        ]
        scraper._client.messages.create.side_effect = [
            _make_text_response(
                "I need to search for more specific job listings...",
                search_urls=["https://de.indeed.com/viewjob?jk=narr1"],
            ),
            _make_text_response(json.dumps(jobs)),
        ]
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert listings[0].title == "AI Eng"
        assert scraper._client.messages.create.call_count == 2

    def test_narrative_followup_failure_raises(self, scraper):
        """When both initial and follow-up responses are narrative, raises RuntimeError."""
        scraper._client.messages.create.side_effect = [
            _make_text_response("Let me search for those jobs..."),
            _make_text_response("I couldn't find any structured results."),
        ]
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
                scraper._search_and_extract("test query", INDEED)

    def test_extracts_json_from_prose(self, scraper):
        jobs = [
            {
                "title": "Data Eng",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=prose1",
            }
        ]
        prose = f"Here are the results:\n{json.dumps(jobs)}\nEnd of results."
        scraper._client.messages.create.return_value = _make_text_response(
            prose,
            search_urls=["https://de.indeed.com/viewjob?jk=prose1"],
        )
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert listings[0].title == "Data Eng"


# ----------------------------------------- URL extraction and filtering tests


class TestExtractSearchResultUrls:
    def test_extracts_urls_from_web_search_results(self):
        response = _make_text_response(
            "[]",
            search_urls=[
                "https://de.indeed.com/viewjob?jk=abc",
                "https://de.indeed.com/viewjob?jk=def",
            ],
        )
        urls = ClaudeScraper._extract_search_result_urls(response)
        assert urls == {
            "https://de.indeed.com/viewjob?jk=abc",
            "https://de.indeed.com/viewjob?jk=def",
        }

    def test_returns_empty_set_for_text_only_response(self):
        response = _make_text_response("[]")
        urls = ClaudeScraper._extract_search_result_urls(response)
        assert urls == set()


class TestValidateListingUrls:
    def test_keeps_valid_job_url_in_search_results(self):
        listings = [
            JobListing(title="Job A", job_url="https://de.indeed.com/viewjob?jk=abc"),
            JobListing(title="Job B", job_url="https://de.indeed.com/viewjob?jk=def"),
        ]
        search_urls = {
            "https://de.indeed.com/viewjob?jk=abc",
            "https://de.indeed.com/viewjob?jk=def",
        }
        result = ClaudeScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 2

    def test_discards_search_page_url(self):
        """URL is in search results but doesn't match job URL pattern."""
        listings = [
            JobListing(
                title="Search Page", job_url="https://de.indeed.com/AI-Engineer-Jobs-in-Berlin"
            ),
        ]
        search_urls = {"https://de.indeed.com/AI-Engineer-Jobs-in-Berlin"}
        result = ClaudeScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 0

    def test_discards_fabricated_url(self):
        """URL is not in search results at all."""
        listings = [
            JobListing(title="Fake", job_url="https://de.indeed.com/viewjob?jk=fake"),
        ]
        search_urls = {"https://de.indeed.com/viewjob?jk=real"}
        result = ClaudeScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 0

    def test_discards_empty_url(self):
        listings = [
            JobListing(title="No URL", job_url=""),
        ]
        search_urls = {"https://de.indeed.com/viewjob?jk=abc"}
        result = ClaudeScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 0

    def test_skips_validation_when_no_search_urls(self):
        listings = [
            JobListing(title="Job", job_url="https://example.com/1"),
        ]
        result = ClaudeScraper._validate_listing_urls(listings, set(), INDEED)
        assert len(result) == 1

    def test_normalizes_trailing_slash(self):
        listings = [
            JobListing(title="Job", job_url="https://www.stepstone.de/jobs/12345/"),
        ]
        search_urls = {"https://www.stepstone.de/jobs/12345"}
        result = ClaudeScraper._validate_listing_urls(
            listings, search_urls, (catalog.get("stepstone"),)
        )
        assert len(result) == 1


# ---------------------------------------------- search_jobs integration tests


def test_search_jobs_raises_on_empty_extraction(scraper, sample_job_search_params, tmp_cache_dir):
    """search_jobs raises RuntimeError when the API returns a valid empty JSON array."""
    scraper._client.messages.create.return_value = _make_text_response("[]")
    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="no job listings could be extracted"):
            scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


def test_search_jobs_raises_when_all_items_filtered(
    scraper, sample_job_search_params, tmp_cache_dir
):
    """search_jobs raises RuntimeError when all extracted items lack required fields."""
    items = [{"company": "A", "location": "Berlin"}, {"company": "B"}]
    scraper._client.messages.create.return_value = _make_text_response(json.dumps(items))
    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="none had the required fields"):
            scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


def test_search_jobs_happy_path(scraper, sample_job_search_params, tmp_cache_dir):
    """search_jobs returns JobListing objects when API returns valid job data."""
    urls = ["https://de.indeed.com/viewjob?jk=abc", "https://de.indeed.com/viewjob?jk=def"]
    jobs = [
        {
            "title": "AI Engineer",
            "company": "TechCo",
            "location": "Berlin",
            "salary_min": 80000,
            "salary_max": 120000,
            "work_type": "Remote",
            "job_board": "Indeed",
            "job_url": urls[0],
        },
        {
            "title": "ML Engineer",
            "company": "DataInc",
            "location": "Munich",
            "salary_min": None,
            "salary_max": None,
            "work_type": "Hybrid",
            "job_board": "Indeed",
            "job_url": urls[1],
        },
    ]
    scraper._client.messages.create.return_value = _make_text_response(
        json.dumps(jobs),
        search_urls=urls,
    )
    with patch("job_research.scraper.time.sleep"):
        result = scraper.search_jobs(sample_job_search_params, tmp_cache_dir)

    assert len(result) == 2
    assert all(isinstance(r, JobListing) for r in result)
    assert result[0].title == "AI Engineer"
    assert result[1].company == "DataInc"
