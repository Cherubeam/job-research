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

import pandas as pd
import pytest

from job_research.analyzer import JobAnalyzer, JobListing
from job_research.jobspy_scraper import JobSpyScraper
from job_research.pipeline import deduplicate
from job_research.salary import parse_salary_range


# ------------------------------------------------------------------------ dedup
#
# F5 (FIXED in Phase 2): the two backends had different dedup rules. There is
# now one implementation in `pipeline.dedup` and these pin its contract.


def test_dedup_collapses_the_same_job_cross_posted_under_two_urls():
    """The case the two old implementations disagreed on."""
    listings = [
        JobListing(title="AI Engineer", company="Acme", location="Berlin", job_url="https://a/1"),
        JobListing(title="AI Engineer", company="Acme", location="Berlin", job_url="https://b/2"),
    ]
    result = deduplicate(listings)
    assert len(result) == 1
    assert result[0].job_url == "https://a/1"  # first occurrence wins


def test_dedup_collapses_identical_urls_whatever_the_title_says():
    listings = [
        JobListing(title="AI Engineer", company="Acme", job_url="https://a/1"),
        JobListing(title="Different Title", company="Other", job_url="https://a/1"),
    ]
    assert len(deduplicate(listings)) == 1


def test_dedup_keeps_the_same_role_in_different_cities():
    """Two cities is two jobs — the old jobspy rule collapsed these."""
    listings = [
        JobListing(title="AI Engineer", company="Acme", location="Berlin", job_url="https://a/1"),
        JobListing(title="AI Engineer", company="Acme", location="Munich", job_url="https://a/2"),
    ]
    assert len(deduplicate(listings)) == 2


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
    assert parse_salary_range(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected", "why"),
    [
        ("35 Std./Woche, 60.000 €", (60000, None), "contract hours are not a salary bound"),
        ("5.000 € pro Monat", (60000, None), "monthly figure annualised"),
        ("25 € / Stunde", (52000, None), "hourly figure annualised"),
        ("2026: 70.000 - 95.000 €", (70000, 95000), "a posting year is not a salary bound"),
    ],
)
def test_salary_parsing_detects_period_and_rejects_non_salary_figures(raw, expected, why):
    """F7 (FIXED in Phase 2): these four all parsed wrong before period detection."""
    assert parse_salary_range(raw) == expected, why


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
def test_salary_survives_every_pandas_dtype(dtype):
    jobspy_scraper = JobSpyScraper(max_jobs=20, country="Germany")
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
