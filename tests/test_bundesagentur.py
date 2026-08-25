"""Tests for the Bundesagentur source.

Fixtures are trimmed from real v6 responses captured on 2026-08-25 with
`scripts/probe_bundesagentur.py`. Nothing here touches the network: the endpoint
is unofficial (ADR-001) and a test suite must not depend on a third party being
up, let alone query it on every CI run.
"""

from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import requests

from job_research.config import JobSearchParams, WorkType
from job_research.sources import bundesagentur as ba

# A posting with structured pay, as returned live.
POSTING_WITH_PAY = {
    "stellenangebotsTitel": "Machine Learning Engineer (m/w/d)",
    "firma": "Orizon GmbH, Niederlassung München Süd",
    "referenznummer": "14751-417A19182-S",
    "datumErsteVeroeffentlichung": "2026-08-24",
    "veroeffentlichungszeitraum": {"von": "2026-08-24"},
    "artDerVerguetung": "GEHALTSSPANNE",
    "verguetungsangabe": "JAHRESGEHALT",
    "gehaltsspanneVon": 79200.0,
    "gehaltsspanneBis": 82800.0,
    "arbeitszeitVollzeit": True,
    "stellenlokationen": [
        {"adresse": {"plz": "80331", "ort": "München", "region": "BAYERN", "land": "DEUTSCHLAND"}}
    ],
}

# Multi-location, no pay stated, and no `homeofficemoeglich` key at all — BA
# omits that field rather than sending false.
POSTING_MULTI_LOCATION = {
    "stellenangebotsTitel": "AI Engineer (m/w/d)",
    "firma": "High-Tech Gründerfonds Management GmbH",
    "referenznummer": "13635-065a56d4_JB5229146-S",
    "datumErsteVeroeffentlichung": "2026-08-25",
    "verguetungsangabe": "KEINE_ANGABEN",
    "arbeitszeitVollzeit": True,
    "stellenlokationen": [
        {"adresse": {"ort": "München", "region": "BAYERN"}},
        {"adresse": {"ort": "Bonn", "region": "NORDRHEIN_WESTFALEN"}},
        {"adresse": {"ort": "Berlingen, Eifel", "region": "RHEINLAND_PFALZ"}},
    ],
}


def _response(payload: dict, status: int = 200) -> Mock:
    mock = Mock()
    mock.json.return_value = payload
    mock.status_code = status
    mock.raise_for_status.return_value = None
    return mock


# ------------------------------------------------------------------- mapping


def test_maps_a_posting_with_structured_pay():
    listing = ba.to_job_listing(POSTING_WITH_PAY)

    assert listing is not None
    assert listing.title == "Machine Learning Engineer (m/w/d)"
    assert listing.company == "Orizon GmbH, Niederlassung München Süd"
    assert listing.location == "München"
    assert (listing.salary_min, listing.salary_max) == (79200, 82800)
    assert listing.posted_date == date(2026, 8, 24)
    assert listing.job_board == "Arbeitsagentur"
    assert listing.job_url == ("https://www.arbeitsagentur.de/jobsuche/jobdetail/14751-417A19182-S")


def test_takes_the_primary_location_from_a_multi_location_posting():
    """One posting, three cities. Joining them would defeat the dedup key."""
    listing = ba.to_job_listing(POSTING_MULTI_LOCATION)
    assert listing is not None
    assert listing.location == "München"


def test_a_posting_without_a_title_is_skipped():
    assert ba.to_job_listing({"firma": "Acme"}) is None


def test_reference_number_is_url_encoded():
    """Some reference numbers contain characters that would break the path."""
    listing = ba.to_job_listing({**POSTING_WITH_PAY, "referenznummer": "abc/def?x=1"})
    assert listing is not None
    assert listing.job_url.endswith("abc%2Fdef%3Fx%3D1")


def test_a_posting_without_a_reference_gets_no_url():
    posting = {k: v for k, v in POSTING_WITH_PAY.items() if k != "referenznummer"}
    listing = ba.to_job_listing(posting)
    assert listing is not None
    assert listing.job_url == ""


def test_falls_back_to_the_publication_period_when_the_date_field_is_absent():
    posting = {k: v for k, v in POSTING_WITH_PAY.items() if k != "datumErsteVeroeffentlichung"}
    listing = ba.to_job_listing(posting)
    assert listing is not None
    assert listing.posted_date == date(2026, 8, 24)


# -------------------------------------------------------------------- salary


def test_no_pay_stated_yields_no_salary():
    listing = ba.to_job_listing(POSTING_MULTI_LOCATION)
    assert listing is not None
    assert (listing.salary_min, listing.salary_max) == (None, None)


def test_fixed_salary_becomes_a_degenerate_range():
    posting = {
        **POSTING_WITH_PAY,
        "artDerVerguetung": "FESTGEHALT",
        "gehaltsspanneVon": None,
        "gehaltsspanneBis": None,
        "festgehalt": 79196.0,
    }
    listing = ba.to_job_listing(posting)
    assert listing is not None
    assert (listing.salary_min, listing.salary_max) == (79196, 79196)


@pytest.mark.parametrize(
    ("period", "expected"),
    [
        ("JAHRESGEHALT", (60000, 60000)),
        ("MONATSGEHALT", (720000, 720000)),
        ("STUNDENLOHN", (60000 * 40 * 52, 60000 * 40 * 52)),
    ],
)
def test_pay_period_is_annualised(period, expected):
    posting = {
        **POSTING_WITH_PAY,
        "verguetungsangabe": period,
        "gehaltsspanneVon": 60000.0,
        "gehaltsspanneBis": 60000.0,
    }
    listing = ba.to_job_listing(posting)
    assert listing is not None
    assert (listing.salary_min, listing.salary_max) == expected


def test_an_unrecognised_pay_period_yields_no_salary():
    """A blank beats an hourly rate silently recorded as an annual salary."""
    posting = {**POSTING_WITH_PAY, "verguetungsangabe": "WOCHENLOHN"}
    listing = ba.to_job_listing(posting)
    assert listing is not None
    assert listing.salary_min is None


# ----------------------------------------------------------------- work type


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ({"homeofficemoeglich": True, "arbeitszeitVollzeit": True}, "Remote"),
        ({"arbeitszeitVollzeit": True}, "Full-time"),
        ({"arbeitszeitTeilzeitFlexibel": True}, "Part-time"),
        ({}, ""),
    ],
)
def test_work_type_from_flags(flags, expected):
    posting = {"stellenangebotsTitel": "X", **flags}
    listing = ba.to_job_listing(posting)
    assert listing is not None
    assert listing.work_type == expected


# -------------------------------------------------------------------- client


@patch("job_research.sources.bundesagentur.requests.get")
def test_client_sends_the_expected_query(mock_get):
    mock_get.return_value = _response({"maxErgebnisse": 1, "ergebnisliste": [POSTING_WITH_PAY]})
    client = ba.JobsucheClient()

    client.search(what="AI Engineer", where="Berlin", published_since_days=7, work_time="ho")

    params = mock_get.call_args.kwargs["params"]
    assert params["was"] == "AI Engineer"
    assert params["wo"] == "Berlin"
    assert params["veroeffentlichtseit"] == 7
    assert params["arbeitszeit"] == "ho"
    assert params["angebotsart"] == 1  # exclude apprenticeships and self-employment
    assert mock_get.call_args.kwargs["headers"]["X-API-Key"] == ba.API_KEY


@patch("job_research.sources.bundesagentur.requests.get")
def test_client_omits_optional_params_when_unset(mock_get):
    mock_get.return_value = _response({"maxErgebnisse": 0, "ergebnisliste": []})
    ba.JobsucheClient().search(what="AI Engineer")

    params = mock_get.call_args.kwargs["params"]
    assert "wo" not in params
    assert "veroeffentlichtseit" not in params
    assert "arbeitszeit" not in params


@patch("job_research.sources.bundesagentur.requests.get")
def test_client_reads_the_retired_v4_shape_too(mock_get):
    """base_url is injectable; a v4-shaped mirror must still parse."""
    mock_get.return_value = _response({"maxErgebnisse": 1, "stellenangebote": [POSTING_WITH_PAY]})
    postings, total = ba.JobsucheClient().search(what="AI Engineer")
    assert len(postings) == 1
    assert total == 1


@patch("job_research.sources.bundesagentur.requests.get")
def test_client_raises_a_diagnostic_error_on_transport_failure(mock_get):
    mock_get.side_effect = requests.ConnectionError("boom")
    with pytest.raises(ba.BundesagenturError, match="unofficial"):
        ba.JobsucheClient().search(what="AI Engineer")


@patch("job_research.sources.bundesagentur.requests.get")
def test_client_raises_on_a_non_json_body(mock_get):
    mock = _response({})
    mock.json.side_effect = ValueError("not json")
    mock_get.return_value = mock
    with pytest.raises(ba.BundesagenturError, match="non-JSON"):
        ba.JobsucheClient().search(what="AI Engineer")


# ------------------------------------------------------------------- scraper


class FakeClient:
    """Returns a fixed page of postings, recording the calls it received."""

    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self.calls: list[dict] = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        index = kwargs.get("page", 1) - 1
        page = self._pages[index] if index < len(self._pages) else []
        return page, sum(len(p) for p in self._pages)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def test_scraper_maps_and_returns_listings(cache_dir):
    client = FakeClient([[POSTING_WITH_PAY, POSTING_MULTI_LOCATION]])
    scraper = ba.BundesagenturScraper(max_jobs=10, client=client)

    listings = scraper.search_jobs(JobSearchParams(keywords="AI Engineer"), cache_dir)

    assert [lst.title for lst in listings] == [
        "Machine Learning Engineer (m/w/d)",
        "AI Engineer (m/w/d)",
    ]


def test_scraper_omits_where_for_a_nationwide_search(cache_dir):
    client = FakeClient([[POSTING_WITH_PAY]])
    params = JobSearchParams(keywords="AI Engineer", location="All of Germany")

    ba.BundesagenturScraper(client=client).search_jobs(params, cache_dir)

    assert client.calls[0]["where"] is None


def test_scraper_maps_remote_work_type_to_the_api_filter(cache_dir):
    client = FakeClient([[POSTING_WITH_PAY]])
    params = JobSearchParams(keywords="AI Engineer", work_type=WorkType.REMOTE)

    ba.BundesagenturScraper(client=client).search_jobs(params, cache_dir)

    assert client.calls[0]["work_time"] == "ho"


def test_scraper_passes_the_recency_window_to_the_api(cache_dir):
    """BA can filter server-side, so this narrows the fetch, not just the result."""
    client = FakeClient([[POSTING_WITH_PAY]])
    params = JobSearchParams(keywords="AI Engineer", posted_within_days=7)

    ba.BundesagenturScraper(client=client).search_jobs(params, cache_dir)

    assert client.calls[0]["published_since_days"] == 7


def test_scraper_stops_at_a_short_page(cache_dir):
    """A page below the page size is the last one; asking for more is wasted."""
    client = FakeClient([[POSTING_WITH_PAY], [POSTING_MULTI_LOCATION]])
    ba.BundesagenturScraper(max_jobs=100, client=client).search_jobs(
        JobSearchParams(keywords="AI Engineer"), cache_dir
    )
    assert len(client.calls) == 1


def test_scraper_never_exceeds_the_page_ceiling(cache_dir):
    """ADR-001: bounded queries only, no bulk enumeration."""
    full_page = [dict(POSTING_WITH_PAY, referenznummer=f"ref-{i}") for i in range(ba.MAX_PAGE_SIZE)]
    client = FakeClient([full_page] * (ba.MAX_PAGES + 3))

    ba.BundesagenturScraper(max_jobs=100_000, client=client).search_jobs(
        JobSearchParams(keywords="AI Engineer"), cache_dir
    )

    assert len(client.calls) == ba.MAX_PAGES


def test_scraper_raises_with_the_coverage_caveat_when_empty(cache_dir):
    """Absence of a BA hit is not evidence that nobody is hiring."""
    client = FakeClient([[]])
    with pytest.raises(ba.BundesagenturError, match="blind"):
        ba.BundesagenturScraper(client=client).search_jobs(
            JobSearchParams(keywords="AI Engineer"), cache_dir
        )


def test_scraper_serves_a_repeat_search_from_cache(cache_dir):
    client = FakeClient([[POSTING_WITH_PAY]])
    scraper = ba.BundesagenturScraper(client=client)
    params = JobSearchParams(keywords="AI Engineer")

    scraper.search_jobs(params, cache_dir)
    scraper.search_jobs(params, cache_dir)

    assert len(client.calls) == 1


def test_recency_window_is_part_of_the_cache_key(cache_dir):
    """It changes the fetch, so it must not replay a wider cached result."""
    client = FakeClient([[POSTING_WITH_PAY]])
    scraper = ba.BundesagenturScraper(client=client)

    scraper.search_jobs(JobSearchParams(keywords="AI Engineer"), cache_dir)
    scraper.search_jobs(JobSearchParams(keywords="AI Engineer", posted_within_days=7), cache_dir)

    assert len(client.calls) == 2
