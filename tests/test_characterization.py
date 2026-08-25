"""Characterization tests — pin CURRENT behaviour, including known-wrong behaviour.

These exist so the refactor phases in `docs/architecture-review.md` change
behaviour *deliberately* rather than by accident. Tests named
`test_characterizes_*` document behaviour we have already decided is wrong; the
finding id (F7, F8, …) says which phase is expected to change them.

**When a `test_characterizes_*` test fails, that is probably correct.** Read the
referenced finding, confirm the new behaviour is the intended one, and rewrite
the test to assert it. Do not patch around the failure.
"""

import csv
import io
from unittest.mock import patch

import pandas as pd
import pytest

from job_research.analyzer import JobAnalyzer, JobListing, _parse_salary_range
from job_research.jobspy_scraper import JobSpyScraper
from job_research.scraper import ClaudeScraper


@pytest.fixture
def claude_scraper() -> ClaudeScraper:
    with patch("job_research.scraper.anthropic.Anthropic"):
        return ClaudeScraper(api_key="sk-test", model="claude-haiku-4-5-20251001", max_jobs=10)


@pytest.fixture
def jobspy_scraper() -> JobSpyScraper:
    return JobSpyScraper(max_jobs=20, country="Germany")


# --------------------------------------------------------------- dedup divergence
#
# F5: the two backends disagree about what a duplicate is. Phase 2 replaces both
# with a single implementation, so these tests pin exactly where they differ.
#
#   ClaudeScraper : URL present -> key on URL ALONE (title+company ignored)
#                   URL absent  -> key on title+company
#   JobSpyScraper : ALWAYS key on title+company, and ADDITIONALLY on URL


def _pair_same_job_different_urls() -> list[JobListing]:
    """The discriminating case: one job, cross-posted under two URLs."""
    return [
        JobListing(title="AI Engineer", company="Acme", job_url="https://a.example/1"),
        JobListing(title="AI Engineer", company="Acme", job_url="https://b.example/2"),
    ]


def test_characterizes_claude_dedup_keeps_same_job_under_two_urls(claude_scraper):
    """F5: Claude keys on URL alone, so a cross-posted job survives twice."""
    result = claude_scraper._deduplicate_listings(_pair_same_job_different_urls())
    assert len(result) == 2


def test_characterizes_jobspy_dedup_collapses_same_job_under_two_urls(jobspy_scraper):
    """F5: JobSpy keys on title+company, so the same job collapses to one."""
    result = jobspy_scraper._deduplicate(_pair_same_job_different_urls())
    assert len(result) == 1
    assert result[0].job_url == "https://a.example/1"  # first wins


@pytest.mark.parametrize("backend", ["claude", "jobspy"])
def test_both_dedups_collapse_identical_urls(backend, claude_scraper, jobspy_scraper):
    """Where they agree: same URL is always a duplicate, whatever the title says."""
    listings = [
        JobListing(title="AI Engineer", company="Acme", job_url="https://a.example/1"),
        JobListing(title="Different Title", company="Other", job_url="https://a.example/1"),
    ]
    dedup = (
        claude_scraper._deduplicate_listings if backend == "claude" else jobspy_scraper._deduplicate
    )
    assert len(dedup(listings)) == 1


@pytest.mark.parametrize("backend", ["claude", "jobspy"])
def test_both_dedups_collapse_title_company_when_url_missing(
    backend, claude_scraper, jobspy_scraper
):
    """Where they agree: with no URL, title+company is the key."""
    listings = [
        JobListing(title="AI Engineer", company="Acme"),
        JobListing(title="ai engineer", company="ACME"),  # case-insensitive
    ]
    dedup = (
        claude_scraper._deduplicate_listings if backend == "claude" else jobspy_scraper._deduplicate
    )
    assert len(dedup(listings)) == 1


# ------------------------------------------------------------------ salary parsing
#
# F7: `_parse_salary_range` takes the first two integers it finds, with no unit
# or period detection. Phase 2 gives it both.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("€70.000 - €95.000", (70000, 95000)),
        ("70000-95000", (70000, 95000)),
        ("70k - 95k", (70000, 95000)),
        ("EUR 80,000 to 120,000", (80000, 120000)),
        ("ab 60.000 €", (60000, None)),
        ("", (None, None)),
        ("competitive", (None, None)),
    ],
)
def test_parse_salary_range_handles_common_formats(raw, expected):
    assert _parse_salary_range(raw) == expected


@pytest.mark.parametrize(
    ("raw", "current_result", "why_wrong"),
    [
        ("35 Std./Woche, 60.000 €", (35, 60000), "hours/week read as the lower bound"),
        ("5.000 € pro Monat", (5000, None), "monthly figure not annualised"),
        ("25 € / Stunde", (25, None), "hourly figure not annualised"),
        ("2026: 70.000 - 95.000 €", (2026, 70000), "leading year read as the lower bound"),
    ],
)
def test_characterizes_salary_parsing_without_unit_detection(raw, current_result, why_wrong):
    """F7: first-two-integers parsing misreads these. Phase 2 should fix them."""
    assert _parse_salary_range(raw) == current_result, why_wrong


# --------------------------------------------------------------------- CSV output
#
# F8 (FIXED in Phase 1): the writer now uses the stdlib `csv` module, so these
# assert correct escaping rather than the old corruption.


def test_csv_escapes_titles_containing_quotes():
    """F8: an embedded double quote survives the round trip."""
    analyzer = JobAnalyzer()
    analyzer.add_listing(JobListing(title='Senior "AI" Engineer', company="Acme"))

    parsed = list(csv.reader(io.StringIO(analyzer.generate_csv_report())))[1]
    assert parsed[0] == 'Senior "AI" Engineer'


def test_csv_escapes_fields_containing_newlines():
    """F8: a newline inside a field stays inside that field."""
    analyzer = JobAnalyzer()
    analyzer.add_listing(JobListing(title="AI Engineer", company="Acme\nGmbH"))

    rows = list(csv.reader(io.StringIO(analyzer.generate_csv_report())))
    assert len(rows) == 2  # header + exactly one row
    assert rows[1][1] == "Acme\nGmbH"


def test_csv_escapes_fields_containing_delimiters():
    analyzer = JobAnalyzer()
    analyzer.add_listing(JobListing(title="AI Engineer, Platform", company="Acme"))

    parsed = list(csv.reader(io.StringIO(analyzer.generate_csv_report())))[1]
    assert parsed[0] == "AI Engineer, Platform"


def test_csv_round_trips_ordinary_fields():
    """Where it works today, and must keep working after Phase 1."""
    analyzer = JobAnalyzer()
    analyzer.add_listing(
        JobListing(
            title="AI Engineer",
            company="Acme GmbH",
            location="Berlin, Germany",
            salary_min=70000,
            salary_max=95000,
            job_board="Indeed",
            job_url="https://example.com/1",
            work_type="Remote",
            posted_date="2026-03-10",
        )
    )
    rows = list(csv.reader(io.StringIO(analyzer.generate_csv_report())))
    assert rows[1] == [
        "AI Engineer",
        "Acme GmbH",
        "Berlin, Germany",
        "70000",
        "95000",
        "EUR",
        "Remote",
        "Indeed",
        "https://example.com/1",
        "2026-03-10",
    ]


# ------------------------------------------------------- pandas dtype coercion
#
# Regression guard: an all-integer pandas column yields numpy.int64, which
# subclasses neither `int` nor `float`. Narrowing on `(int, float)` silently
# drops every salary. The existing fixtures all contain NaN, which makes the
# column float64 and hides this.


@pytest.mark.parametrize("dtype", ["int64", "float64", "object"])
def test_salary_survives_every_pandas_dtype(jobspy_scraper, dtype):
    row = pd.DataFrame(
        {
            "title": ["AI Engineer"],
            "company": ["Acme"],
            "location": ["Berlin"],
            "min_amount": pd.Series([70000], dtype=dtype),
            "max_amount": pd.Series([95000], dtype=dtype),
            "job_url": ["https://example.com/1"],
            "description": [""],
            "date_posted": ["2026-03-10"],
            "is_remote": [False],
            "job_type": ["fulltime"],
            "site": ["indeed"],
        }
    ).iloc[0]

    listing = jobspy_scraper._to_job_listing(row)

    assert listing is not None
    assert (listing.salary_min, listing.salary_max) == (70000, 95000)
