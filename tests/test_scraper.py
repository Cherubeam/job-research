"""Tests for scraper.py

The scraper is provider-agnostic, so these drive it through a `FakeProvider`
rather than mocking a vendor SDK. The vendor-shaped behaviour those mocks used
to cover — retries, rate limits, pulling citation URLs out of a response — now
lives in `test_providers.py`, tested against each provider directly.
"""

import json

import pytest
from pydantic import ValidationError

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams
from job_research.providers import SearchResponse
from job_research.scraper import LLMScraper
from job_research.sources import Backend, catalog


class FakeProvider:
    """A `SearchProvider` that replays queued responses and records its calls."""

    name = "fake"
    model = "fake/model-1"

    def __init__(self) -> None:
        self.search_responses: list[SearchResponse | Exception] = []
        self.complete_responses: list[str] = []
        self.search_calls: list[dict] = []
        self.complete_calls: list[dict] = []

    # -- queueing helpers, so tests read as "the model said X, search found Y"

    def will_search(self, text: str, urls: list[str] | None = None) -> "FakeProvider":
        self.search_responses.append(SearchResponse(text=text, result_urls=set(urls or [])))
        return self

    def will_fail(self, exc: Exception) -> "FakeProvider":
        self.search_responses.append(exc)
        return self

    def will_complete(self, text: str) -> "FakeProvider":
        self.complete_responses.append(text)
        return self

    # -- SearchProvider

    def search(self, *, system, messages, allowed_domains, max_searches) -> SearchResponse:
        self.search_calls.append(
            {
                "system": system,
                "messages": list(messages),
                "allowed_domains": list(allowed_domains),
                "max_searches": max_searches,
            }
        )
        assert self.search_responses, "unexpected extra search() call"
        queued = self.search_responses.pop(0)
        if isinstance(queued, Exception):
            raise queued
        return queued

    def complete(self, *, system, messages) -> str:
        self.complete_calls.append({"system": system, "messages": list(messages)})
        assert self.complete_responses, "unexpected extra complete() call"
        return self.complete_responses.pop(0)


INDEED = (catalog.get("indeed"),)


@pytest.fixture
def provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def scraper(provider: FakeProvider) -> LLMScraper:
    return LLMScraper(provider, max_jobs=10)


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


# ---------------------------------------------------------------- query/prompt


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
    assert "copied verbatim from a web search result" in prompt


def test_build_system_prompt_contains_expired_listing_rule(scraper):
    prompt = scraper._build_system_prompt(INDEED)
    assert "expired" in prompt
    assert "abgelaufen" in prompt


def test_default_selection_resolves_to_the_registry_defaults():
    sources = catalog.resolve(JobSearchParams().enabled_sources, Backend.LLM)
    assert {s.id for s in sources} == {"indeed", "arbeitsagentur"}


def test_explicit_selection_is_honoured():
    params = JobSearchParams(enabled_sources=["stepstone", "indeed"])
    sources = catalog.resolve(params.enabled_sources, Backend.LLM)
    assert {s.id for s in sources} == {"stepstone", "indeed"}


def test_search_jobs_rejects_a_selection_this_backend_cannot_reach(scraper, tmp_cache_dir):
    """Selecting nothing reachable must fail loudly, not silently search nothing."""
    params = JobSearchParams(enabled_sources=[])
    with pytest.raises(RuntimeError, match="No sources selected"):
        scraper.search_jobs(params, tmp_cache_dir)


def test_search_jobs_propagates_provider_failures(
    scraper, provider, sample_job_search_params, tmp_cache_dir
):
    """A provider failure must surface, so the orchestrator reports the source as failed."""
    provider.will_fail(RuntimeError("boom"))
    with pytest.raises(RuntimeError, match="boom"):
        scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


# ------------------------------------------------------ what the provider gets


def test_search_restricts_the_provider_to_the_selected_domains(scraper, provider):
    """The domain allowlist is the whole point of per-source search — assert it is passed."""
    provider.will_search("[]")
    scraper._search_and_extract("test query", (catalog.get("stepstone"), catalog.get("monster")))
    assert provider.search_calls[0]["allowed_domains"] == ["stepstone.de", "monster.de"]


def test_search_passes_the_platform_hints_for_the_selected_sources(scraper, provider):
    provider.will_search("[]")
    scraper._search_and_extract("test query", (catalog.get("stepstone"),))
    assert "stellenangebote--" in provider.search_calls[0]["system"]


# -------------------------------------------------- _search_and_extract tests


class TestSearchAndExtract:
    def test_returns_listings_matching_search_urls(self, scraper, provider):
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
        provider.will_search(json.dumps(jobs), ["https://de.indeed.com/viewjob?jk=abc123"])
        listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert total == 1
        assert listings[0].title == "AI Engineer"

    def test_filters_fabricated_urls(self, scraper, provider):
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
        provider.will_search(json.dumps(jobs), ["https://de.indeed.com/viewjob?jk=real123"])
        listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert listings[0].title == "Real Job"
        assert total == 2

    def test_raises_on_no_text(self, scraper, provider):
        provider.will_search("", ["https://de.indeed.com/viewjob?jk=abc"])
        with pytest.raises(RuntimeError, match="no text content"):
            scraper._search_and_extract("test query", INDEED)

    def test_raises_on_empty_text(self, scraper, provider):
        provider.will_search("   ")
        with pytest.raises(RuntimeError, match="no text content"):
            scraper._search_and_extract("test query", INDEED)

    def test_names_the_provider_when_it_returns_nothing(self, scraper, provider):
        """The error has to say who was silent, or a provider switch is invisible."""
        provider.will_search("")
        with pytest.raises(RuntimeError, match="fake"):
            scraper._search_and_extract("test query", INDEED)

    def test_raises_on_invalid_json_after_retry(self, scraper, provider):
        """Both initial response and follow-up retry return non-JSON text."""
        provider.will_search("not json at all").will_complete("still not json")
        with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
            scraper._search_and_extract("test query", INDEED)

    def test_raises_on_non_array(self, scraper, provider):
        provider.will_search('{"not": "array"}').will_complete('{"still": "not array"}')
        with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
            scraper._search_and_extract("test query", INDEED)

    def test_strips_markdown_fences(self, scraper, provider):
        jobs = [
            {
                "title": "ML Eng",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=fence1",
            }
        ]
        provider.will_search(
            f"```json\n{json.dumps(jobs)}\n```", ["https://de.indeed.com/viewjob?jk=fence1"]
        )
        listings, _ = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert listings[0].title == "ML Eng"

    def test_skips_invalid_items(self, scraper, provider):
        items = [
            {
                "title": "Valid Job",
                "company": "Co",
                "job_url": "https://de.indeed.com/viewjob?jk=valid",
            },
            {"company": "No Title"},  # missing title → ValidationError
            {"title": "", "company": "Empty Title"},  # empty title → ValidationError
        ]
        provider.will_search(json.dumps(items), ["https://de.indeed.com/viewjob?jk=valid"])
        listings, total = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert total == 3
        assert listings[0].title == "Valid Job"

    def test_narrative_response_triggers_followup(self, scraper, provider):
        """When initial response is narrative, a follow-up call extracts JSON."""
        jobs = [
            {
                "title": "AI Eng",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=narr1",
            }
        ]
        provider.will_search(
            "I need to search for more specific job listings...",
            ["https://de.indeed.com/viewjob?jk=narr1"],
        ).will_complete(json.dumps(jobs))

        listings, _ = scraper._search_and_extract("test query", INDEED)

        assert len(listings) == 1
        assert listings[0].title == "AI Eng"
        assert len(provider.complete_calls) == 1

    def test_followup_replays_the_narrative_answer(self, scraper, provider):
        """The re-ask only works if the model can see what it already wrote."""
        provider.will_search("Here is some prose").will_complete("[]")
        scraper._search_and_extract("test query", INDEED)
        replayed = provider.complete_calls[0]["messages"]
        assert replayed[1] == {"role": "assistant", "content": "Here is some prose"}

    def test_narrative_followup_failure_raises(self, scraper, provider):
        """When both initial and follow-up responses are narrative, raises RuntimeError."""
        provider.will_search("Let me search for those jobs...").will_complete(
            "I couldn't find any structured results."
        )
        with pytest.raises(RuntimeError, match="Failed to parse job listings after retry"):
            scraper._search_and_extract("test query", INDEED)

    def test_extracts_json_from_prose(self, scraper, provider):
        jobs = [
            {
                "title": "Data Eng",
                "company": "Co",
                "location": "Berlin",
                "job_url": "https://de.indeed.com/viewjob?jk=prose1",
            }
        ]
        provider.will_search(
            f"Here are the results:\n{json.dumps(jobs)}\nEnd of results.",
            ["https://de.indeed.com/viewjob?jk=prose1"],
        )
        listings, _ = scraper._search_and_extract("test query", INDEED)
        assert len(listings) == 1
        assert listings[0].title == "Data Eng"


# ------------------------------------------------------ URL filtering (shared)


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
        result = LLMScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 2

    def test_discards_search_page_url(self):
        """URL is in search results but doesn't match job URL pattern."""
        listings = [
            JobListing(
                title="Search Page", job_url="https://de.indeed.com/AI-Engineer-Jobs-in-Berlin"
            ),
        ]
        search_urls = {"https://de.indeed.com/AI-Engineer-Jobs-in-Berlin"}
        result = LLMScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 0

    def test_discards_fabricated_url(self):
        """URL is not in search results at all."""
        listings = [
            JobListing(title="Fake", job_url="https://de.indeed.com/viewjob?jk=fake"),
        ]
        search_urls = {"https://de.indeed.com/viewjob?jk=real"}
        result = LLMScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 0

    def test_discards_empty_url(self):
        listings = [
            JobListing(title="No URL", job_url=""),
        ]
        search_urls = {"https://de.indeed.com/viewjob?jk=abc"}
        result = LLMScraper._validate_listing_urls(listings, search_urls, INDEED)
        assert len(result) == 0

    def test_skips_validation_when_no_search_urls(self):
        listings = [
            JobListing(title="Job", job_url="https://example.com/1"),
        ]
        result = LLMScraper._validate_listing_urls(listings, set(), INDEED)
        assert len(result) == 1

    def test_normalizes_trailing_slash(self):
        listings = [
            JobListing(title="Job", job_url="https://www.stepstone.de/jobs/12345/"),
        ]
        search_urls = {"https://www.stepstone.de/jobs/12345"}
        result = LLMScraper._validate_listing_urls(
            listings, search_urls, (catalog.get("stepstone"),)
        )
        assert len(result) == 1


# ---------------------------------------------- search_jobs integration tests


def test_search_jobs_raises_on_empty_extraction(
    scraper, provider, sample_job_search_params, tmp_cache_dir
):
    """search_jobs raises RuntimeError when the model returns a valid empty JSON array."""
    provider.will_search("[]")
    with pytest.raises(RuntimeError, match="no job listings could be extracted"):
        scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


def test_search_jobs_raises_when_all_items_filtered(
    scraper, provider, sample_job_search_params, tmp_cache_dir
):
    """search_jobs raises RuntimeError when all extracted items lack required fields."""
    items = [{"company": "A", "location": "Berlin"}, {"company": "B"}]
    provider.will_search(json.dumps(items))
    with pytest.raises(RuntimeError, match="none had the required fields"):
        scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


def test_search_jobs_happy_path(scraper, provider, sample_job_search_params, tmp_cache_dir):
    """search_jobs returns JobListing objects when the model returns valid job data."""
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
    provider.will_search(json.dumps(jobs), urls)

    result = scraper.search_jobs(sample_job_search_params, tmp_cache_dir)

    assert len(result) == 2
    assert all(isinstance(r, JobListing) for r in result)
    assert result[0].title == "AI Engineer"
    assert result[1].company == "DataInc"


def test_cache_is_not_shared_between_providers(sample_job_search_params, tmp_cache_dir):
    """Switching provider or model must re-fetch, not replay the other one's results.

    Without provider/model in the cache key, changing OPENROUTER_MODEL would
    appear to do nothing for 24 hours.
    """
    urls = ["https://de.indeed.com/viewjob?jk=abc"]
    job = json.dumps([{"title": "AI Engineer", "company": "TechCo", "job_url": urls[0]}])

    first = FakeProvider()
    first.will_search(job, urls)
    LLMScraper(first, max_jobs=10).search_jobs(sample_job_search_params, tmp_cache_dir)

    second = FakeProvider()
    second.model = "other/model-2"
    second.will_search(job, urls)
    LLMScraper(second, max_jobs=10).search_jobs(sample_job_search_params, tmp_cache_dir)

    assert len(second.search_calls) == 1, "second provider served from the first one's cache"
