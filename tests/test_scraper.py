"""Tests for scraper.py"""

import json

import pytest
from pydantic import ValidationError
from unittest.mock import MagicMock, patch

from job_research.analyzer import JobListing
from job_research.config import JobBoardConfig
from job_research.scraper import ClaudeScraper


def _make_text_response(text: str) -> MagicMock:
    """Build a mock API response containing a single text block."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    return response


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

@pytest.mark.parametrize("salary_str_min,salary_str_max,expected_min,expected_max", [
    ("€80.000", "120.000", 80000, 120000),
    ("70k", "100k", 70000, 100000),
    ("ab 80000 EUR", None, 80000, None),
])
def test_salary_coercion_from_strings(salary_str_min, salary_str_max, expected_min, expected_max):
    listing = JobListing(
        title="Eng",
        salary_min=salary_str_min,  # type: ignore[arg-type]
        salary_max=salary_str_max,  # type: ignore[arg-type]
    )
    assert listing.salary_min == expected_min
    assert listing.salary_max == expected_max


# --------------------------------------------------------------- deduplication

def test_deduplicate_by_url(scraper):
    listings = [
        JobListing(title="AI Eng", company="A", location="Berlin", job_url="https://example.com/1"),
        JobListing(title="AI Eng", company="A", location="Berlin", job_url="https://example.com/1"),
        JobListing(title="ML Eng", company="B", location="Munich", job_url="https://example.com/2"),
    ]
    result = scraper._deduplicate_listings(listings)
    assert len(result) == 2


def test_deduplicate_by_title_company(scraper):
    listings = [
        JobListing(title="AI Engineer", company="TechCorp", location="Berlin", job_url=""),
        JobListing(title="AI Engineer", company="TechCorp", location="Hamburg", job_url=""),
        JobListing(title="ML Engineer", company="TechCorp", location="Berlin", job_url=""),
    ]
    result = scraper._deduplicate_listings(listings)
    assert len(result) == 2


# ---------------------------------------------------------- build_search_query

def test_build_search_query_contains_keywords(scraper, sample_job_search_params):
    query = scraper._build_search_query(sample_job_search_params)
    assert "AI Engineer" in query
    assert "Berlin" in query


def test_build_search_query_excludes_site_clause(scraper, sample_job_search_params):
    query = scraper._build_search_query(sample_job_search_params)
    assert "site:" not in query


def test_active_boards_stored_on_scraper(sample_job_search_params):
    with patch("job_research.scraper.anthropic.Anthropic"):
        s = ClaudeScraper(api_key="sk-test", model="claude-haiku-4-5-20251001")
    assert "stepstone.de" in s._boards
    assert "linkedin.com" in s._boards
    assert "arbeitsagentur.de" in s._boards


def test_disabled_board_excluded_from_boards(sample_job_search_params):
    board_config = JobBoardConfig(search_stepstone=False)
    with patch("job_research.scraper.anthropic.Anthropic"):
        s = ClaudeScraper(api_key="sk-test", model="claude-haiku-4-5-20251001", board_config=board_config)
    assert "stepstone.de" not in s._boards
    assert "linkedin.com" in s._boards


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
    error = anthropic_module.RateLimitError(
        "rate limited", response=response_mock, body={}
    )
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
    error = anthropic_module.RateLimitError(
        "rate limited", response=response_mock, body={}
    )
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
    def test_returns_listings(self, scraper):
        jobs = [
            {"title": "AI Engineer", "company": "TechCo", "location": "Berlin",
             "salary_min": 80000, "salary_max": 120000, "work_type": "Remote",
             "job_board": "StepStone", "job_url": "https://example.com/1"},
        ]
        scraper._client.messages.create.return_value = _make_text_response(json.dumps(jobs))
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query")
        assert len(listings) == 1
        assert total == 1
        assert listings[0].title == "AI Engineer"

    def test_raises_on_no_text(self, scraper):
        response = MagicMock()
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        response.content = [tool_block]
        scraper._client.messages.create.return_value = response
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="no text content"):
                scraper._search_and_extract("test query")

    def test_raises_on_empty_text(self, scraper):
        scraper._client.messages.create.return_value = _make_text_response("   ")
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="no text content"):
                scraper._search_and_extract("test query")

    def test_raises_on_invalid_json_after_retry(self, scraper):
        """Both initial response and follow-up retry return non-JSON text."""
        scraper._client.messages.create.side_effect = [
            _make_text_response("not json at all"),
            _make_text_response("still not json"),
        ]
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
                scraper._search_and_extract("test query")

    def test_raises_on_non_array(self, scraper):
        scraper._client.messages.create.side_effect = [
            _make_text_response('{"not": "array"}'),
            _make_text_response('{"still": "not array"}'),
        ]
        with patch("job_research.scraper.time.sleep"):
            with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
                scraper._search_and_extract("test query")

    def test_strips_markdown_fences(self, scraper):
        jobs = [{"title": "ML Eng", "company": "Co", "location": "Berlin"}]
        fenced = f"```json\n{json.dumps(jobs)}\n```"
        scraper._client.messages.create.return_value = _make_text_response(fenced)
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query")
        assert len(listings) == 1
        assert listings[0].title == "ML Eng"

    def test_skips_invalid_items(self, scraper):
        items = [
            {"title": "Valid Job", "company": "Co"},
            {"company": "No Title"},  # missing title → ValidationError
            {"title": "", "company": "Empty Title"},  # empty title → ValidationError
        ]
        scraper._client.messages.create.return_value = _make_text_response(json.dumps(items))
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query")
        assert len(listings) == 1
        assert total == 3
        assert listings[0].title == "Valid Job"

    def test_narrative_response_triggers_followup(self, scraper):
        """When initial response is narrative, a follow-up call extracts JSON."""
        jobs = [{"title": "AI Eng", "company": "Co", "location": "Berlin"}]
        scraper._client.messages.create.side_effect = [
            _make_text_response("I need to search for more specific job listings..."),
            _make_text_response(json.dumps(jobs)),
        ]
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query")
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
                scraper._search_and_extract("test query")

    def test_extracts_json_from_prose(self, scraper):
        jobs = [{"title": "Data Eng", "company": "Co", "location": "Berlin"}]
        prose = f"Here are the results:\n{json.dumps(jobs)}\nEnd of results."
        scraper._client.messages.create.return_value = _make_text_response(prose)
        with patch("job_research.scraper.time.sleep"):
            listings, total = scraper._search_and_extract("test query")
        assert len(listings) == 1
        assert listings[0].title == "Data Eng"


# ---------------------------------------------- search_jobs integration tests

def test_search_jobs_raises_on_empty_extraction(scraper, sample_job_search_params, tmp_cache_dir):
    """search_jobs raises RuntimeError when the API returns a valid empty JSON array."""
    scraper._client.messages.create.return_value = _make_text_response("[]")
    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="no job listings could be extracted"):
            scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


def test_search_jobs_raises_when_all_items_filtered(scraper, sample_job_search_params, tmp_cache_dir):
    """search_jobs raises RuntimeError when all extracted items lack required fields."""
    items = [{"company": "A", "location": "Berlin"}, {"company": "B"}]
    scraper._client.messages.create.return_value = _make_text_response(json.dumps(items))
    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="none had the required fields"):
            scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


def test_search_jobs_happy_path(scraper, sample_job_search_params, tmp_cache_dir):
    """search_jobs returns JobListing objects when API returns valid job data."""
    jobs = [
        {"title": "AI Engineer", "company": "TechCo", "location": "Berlin",
         "salary_min": 80000, "salary_max": 120000, "work_type": "Remote",
         "job_board": "StepStone", "job_url": "https://example.com/1"},
        {"title": "ML Engineer", "company": "DataInc", "location": "Munich",
         "salary_min": None, "salary_max": None, "work_type": "Hybrid",
         "job_board": "LinkedIn", "job_url": "https://example.com/2"},
    ]
    scraper._client.messages.create.return_value = _make_text_response(json.dumps(jobs))
    with patch("job_research.scraper.time.sleep"):
        result = scraper.search_jobs(sample_job_search_params, tmp_cache_dir)

    assert len(result) == 2
    assert all(isinstance(r, JobListing) for r in result)
    assert result[0].title == "AI Engineer"
    assert result[1].company == "DataInc"
