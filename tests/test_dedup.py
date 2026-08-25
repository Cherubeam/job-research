"""Tests for pipeline.dedup — the single cross-source deduplication rule."""

import pytest

from job_research.analyzer import JobListing
from job_research.pipeline import dedup


def _listing(title="AI Engineer", company="Acme", location="Berlin", url="") -> JobListing:
    return JobListing(title=title, company=company, location=location, job_url=url)


# ------------------------------------------------------------- normalization


@pytest.mark.parametrize(
    "location",
    ["Berlin", "Berlin, Germany", "Berlin, Berlin, Deutschland", "  berlin  ", "Berlin (Remote)"],
)
def test_location_variants_normalize_together(location):
    assert dedup.normalize_location(location) == "berlin"


def test_different_cities_stay_distinct():
    assert dedup.normalize_location("Berlin") != dedup.normalize_location("Munich")


@pytest.mark.parametrize(
    "title",
    [
        "AI Engineer (m/w/d)",
        "AI Engineer (w/m/d)",
        "AI Engineer m/w/d",
        "AI Engineer (all genders)",
        "ai engineer",
    ],
)
def test_gender_markers_do_not_affect_identity(title):
    assert dedup.identity(_listing(title=title)) == dedup.identity(_listing(title="AI Engineer"))


# ------------------------------------------------------------------- dedup


def test_empty_input():
    assert dedup.deduplicate([]) == []


def test_keeps_the_first_occurrence():
    first = _listing(url="https://a/1")
    second = _listing(url="https://b/2")
    assert dedup.deduplicate([first, second]) == [first]


def test_collapses_the_same_url():
    listings = [_listing(url="https://a/1"), _listing(title="Other", url="https://a/1")]
    assert len(dedup.deduplicate(listings)) == 1


def test_collapses_urls_differing_only_by_fragment_or_trailing_slash():
    listings = [
        _listing(title="A", url="https://example.com/job/1"),
        _listing(title="B", url="https://example.com/job/1/"),
        _listing(title="C", url="https://example.com/job/1#apply"),
    ]
    assert len(dedup.deduplicate(listings)) == 1


def test_collapses_the_same_posting_cross_listed_under_different_urls():
    """The whole point: one job appearing on Indeed and LinkedIn."""
    listings = [
        _listing(url="https://de.indeed.com/viewjob?jk=1"),
        _listing(title="AI Engineer (m/w/d)", url="https://linkedin.com/jobs/view/2"),
    ]
    assert len(dedup.deduplicate(listings)) == 1


def test_keeps_the_same_role_in_different_cities():
    listings = [
        _listing(location="Berlin", url="https://a/1"),
        _listing(location="Munich", url="https://a/2"),
    ]
    assert len(dedup.deduplicate(listings)) == 2


def test_keeps_the_same_role_at_different_companies():
    listings = [
        _listing(company="Acme", url="https://a/1"),
        _listing(company="Globex", url="https://a/2"),
    ]
    assert len(dedup.deduplicate(listings)) == 2


def test_collapses_listings_without_urls_by_identity():
    assert len(dedup.deduplicate([_listing(), _listing()])) == 1


def test_a_missing_url_does_not_collide_with_another_missing_url():
    """Empty URLs must not all look like "the same URL"."""
    listings = [_listing(company="Acme"), _listing(company="Globex")]
    assert len(dedup.deduplicate(listings)) == 2


def test_url_match_wins_even_when_identity_differs():
    """Same URL is the same posting, however inconsistently it was transcribed."""
    listings = [
        _listing(title="AI Engineer", company="Acme", url="https://a/1"),
        _listing(title="KI-Ingenieur", company="Acme GmbH", url="https://a/1"),
    ]
    assert len(dedup.deduplicate(listings)) == 1


def test_order_is_otherwise_preserved():
    listings = [
        _listing(company="A", url="https://a/1"),
        _listing(company="B", url="https://a/2"),
        _listing(company="A", url="https://a/1"),
        _listing(company="C", url="https://a/3"),
    ]
    assert [lst.company for lst in dedup.deduplicate(listings)] == ["A", "B", "C"]
