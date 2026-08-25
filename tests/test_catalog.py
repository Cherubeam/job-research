"""Tests for the source registry."""

import pytest

from job_research.sources import Backend, catalog


# --------------------------------------------------------- registry integrity


def test_source_ids_are_unique():
    ids = [s.id for s in catalog.all_sources()]
    assert len(ids) == len(set(ids))


def test_every_source_declares_at_least_one_backend():
    for source in catalog.all_sources():
        assert source.backends, f"{source.id} is unreachable by any backend"


def test_jobspy_capable_sources_declare_a_site_name():
    """A source jobspy can serve is useless without the name jobspy knows it by."""
    for source in catalog.for_backend(Backend.JOBSPY):
        assert source.jobspy_site, f"{source.id} claims jobspy support but has no jobspy_site"


def test_claude_capable_sources_declare_a_search_hint():
    for source in catalog.for_backend(Backend.CLAUDE):
        assert source.search_hint, f"{source.id} has no search hint for the Claude prompt"


def test_every_backend_can_reach_at_least_one_default_source():
    """Whichever backend is configured, a default run must have something to search."""
    for backend in Backend:
        resolved = catalog.resolve(sorted(catalog.DEFAULT_ENABLED), backend)
        assert resolved, f"{backend.value} has no default-on source it can reach"


def test_google_jobs_is_off_by_default_and_carries_its_caveat():
    """ADR-003: querying Google Search automatically is restricted by its terms."""
    source = catalog.get("google")
    assert not source.default_enabled
    assert "003-google-jobs" in source.caveat


def test_default_on_sources():
    """Indeed and Arbeitsagentur. LinkedIn stays opt-in per ADR-002."""
    assert catalog.DEFAULT_ENABLED == frozenset({"indeed", "arbeitsagentur"})


def test_linkedin_is_off_by_default_and_carries_its_caveat():
    source = catalog.get("linkedin")
    assert not source.default_enabled
    assert "002-linkedin-scraping" in source.caveat


def test_arbeitsagentur_still_carries_its_caveat_though_enabled():
    """ADR-001 amendment: on by default, but the caveat must stay visible."""
    source = catalog.get("arbeitsagentur")
    assert source.default_enabled
    assert "001-bundesagentur-terms-of-use" in source.caveat


# ------------------------------------------------------------------- lookup


def test_get_returns_the_source():
    assert catalog.get("indeed").domain == "de.indeed.com"


def test_get_raises_a_helpful_error_for_an_unknown_id():
    with pytest.raises(catalog.UnknownSourceError) as exc:
        catalog.get("stepstoen")
    assert "stepstone" in str(exc.value)  # lists the known ids


def test_for_backend_filters_by_capability():
    jobspy_ids = {s.id for s in catalog.for_backend(Backend.JOBSPY)}
    claude_ids = {s.id for s in catalog.for_backend(Backend.CLAUDE)}
    assert jobspy_ids == {"indeed", "linkedin", "google"}
    assert "stepstone" in claude_ids
    assert "stepstone" not in jobspy_ids


# ------------------------------------------------------------------ resolve


def test_resolve_keeps_only_what_the_backend_can_reach():
    """Switching backend should quietly search less, not fail."""
    resolved = catalog.resolve(["stepstone", "indeed"], Backend.JOBSPY)
    assert [s.id for s in resolved] == ["indeed"]


def test_resolve_preserves_the_requested_order():
    resolved = catalog.resolve(["linkedin", "indeed"], Backend.CLAUDE)
    assert [s.id for s in resolved] == ["linkedin", "indeed"]


def test_resolve_raises_on_an_unknown_id():
    """A backend mismatch is expected; a typo is a configuration error."""
    with pytest.raises(catalog.UnknownSourceError):
        catalog.resolve(["indeed", "nope"], Backend.CLAUDE)


def test_resolve_of_nothing_is_empty():
    assert catalog.resolve([], Backend.CLAUDE) == ()


# ------------------------------------------------------------ URL patterns


@pytest.mark.parametrize(
    ("source_id", "url"),
    [
        ("indeed", "https://de.indeed.com/viewjob?jk=abc123"),
        ("indeed", "https://de.indeed.com/rc/clk?jk=abc123"),
        ("linkedin", "https://linkedin.com/jobs/view/4012345678"),
        ("stepstone", "https://www.stepstone.de/stellenangebote--AI-Engineer--123.html"),
        ("stepstone", "https://www.stepstone.de/jobs/12345"),
    ],
)
def test_accepts_individual_listing_urls(source_id, url):
    assert catalog.get(source_id).is_job_listing_url(url)


@pytest.mark.parametrize(
    ("source_id", "url"),
    [
        ("indeed", "https://de.indeed.com/jobs?q=AI+Engineer"),
        ("indeed", "https://de.indeed.com/Karriere-in-Berlin"),
        ("linkedin", "https://linkedin.com/jobs/search?keywords=ai"),
        ("stepstone", "https://www.stepstone.de/jobs/ai-engineer/in-berlin"),
    ],
)
def test_rejects_search_and_category_urls(source_id, url):
    """These are the pages that produced fabricated-looking results before."""
    assert not catalog.get(source_id).is_job_listing_url(url)


def test_a_source_does_not_match_another_sources_url():
    assert not catalog.get("indeed").is_job_listing_url("https://linkedin.com/jobs/view/1")
