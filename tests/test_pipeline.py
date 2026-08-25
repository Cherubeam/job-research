"""Tests for pipeline.py — post-fetch filtering, interleaving, and truncation."""

import pytest

from job_research import pipeline
from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, SeniorityLevel


def _listing(title: str = "AI Engineer", **kwargs) -> JobListing:
    return JobListing(title=title, **kwargs)


# ------------------------------------------------------------------ seniority


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Junior AI Engineer", SeniorityLevel.JUNIOR),
        ("Werkstudent Machine Learning (m/w/d)", SeniorityLevel.JUNIOR),
        ("Praktikum Data Science", SeniorityLevel.JUNIOR),
        ("Trainee Software Engineering", SeniorityLevel.JUNIOR),
        ("Senior AI Engineer", SeniorityLevel.SENIOR),
        ("Lead Data Scientist", SeniorityLevel.SENIOR),
        ("Head of Machine Learning", SeniorityLevel.SENIOR),
        ("Teamleiter Softwareentwicklung", SeniorityLevel.SENIOR),
        ("Principal ML Engineer", SeniorityLevel.SENIOR),
        ("Projektleiterin Data Platform", SeniorityLevel.SENIOR),
        ("Abteilungsleitung IT", SeniorityLevel.SENIOR),
        ("AI Engineer", SeniorityLevel.MID_LEVEL),
        ("Machine Learning Engineer (m/w/d)", SeniorityLevel.MID_LEVEL),
    ],
)
def test_infer_seniority(title, expected):
    assert pipeline.infer_seniority(title) == expected


def test_infer_seniority_prefers_junior_over_senior_marker():
    """ "Junior Architect" is junior, not senior."""
    assert pipeline.infer_seniority("Junior Architect") == SeniorityLevel.JUNIOR


def test_infer_seniority_ignores_compound_false_friends():
    """ "Begleiter" ends in "leiter" but means companion, not manager."""
    assert pipeline.infer_seniority("Kundenbegleiter Vertrieb") == SeniorityLevel.MID_LEVEL


def test_infer_seniority_matches_whole_words_only():
    """ "leadership" must not read as "lead"."""
    assert pipeline.infer_seniority("Engineer, Leadership Program") == SeniorityLevel.MID_LEVEL


def test_filter_by_seniority_all_is_a_passthrough():
    listings = [_listing("Junior AI Engineer"), _listing("Senior AI Engineer")]
    assert pipeline.filter_by_seniority(listings, SeniorityLevel.ALL) == listings


def test_filter_by_seniority_keeps_only_the_requested_level():
    listings = [
        _listing("Junior AI Engineer"),
        _listing("AI Engineer"),
        _listing("Senior AI Engineer"),
    ]
    result = pipeline.filter_by_seniority(listings, SeniorityLevel.SENIOR)
    assert [lst.title for lst in result] == ["Senior AI Engineer"]


def test_filter_by_seniority_mid_level_excludes_marked_titles():
    listings = [
        _listing("Junior AI Engineer"),
        _listing("AI Engineer"),
        _listing("Senior AI Engineer"),
    ]
    result = pipeline.filter_by_seniority(listings, SeniorityLevel.MID_LEVEL)
    assert [lst.title for lst in result] == ["AI Engineer"]


# --------------------------------------------------------------------- salary


def test_filter_by_salary_keeps_listings_without_salary_information():
    """Most German postings omit salary; dropping them would gut the results."""
    listings = [_listing("AI Engineer")]
    assert pipeline.filter_by_salary(listings, 50000, 200000) == listings


@pytest.mark.parametrize(
    ("salary_min", "salary_max", "kept"),
    [
        (60000, 90000, True),  # fully inside
        (40000, 60000, True),  # overlaps the lower edge
        (190000, 250000, True),  # overlaps the upper edge
        (10000, 40000, False),  # entirely below
        (210000, 300000, False),  # entirely above
        (50000, 200000, True),  # exactly the window
    ],
)
def test_filter_by_salary_overlap(salary_min, salary_max, kept):
    listings = [_listing(salary_min=salary_min, salary_max=salary_max)]
    result = pipeline.filter_by_salary(listings, 50000, 200000)
    assert bool(result) is kept


def test_filter_by_salary_treats_open_ended_lower_bound_as_unbounded_above():
    """ "ab 60.000 €" parses to (60000, None) and could pay anything above it."""
    listings = [_listing(salary_min=60000, salary_max=None)]
    assert pipeline.filter_by_salary(listings, 150000, 200000) == listings


def test_filter_by_salary_rejects_open_ended_bound_below_the_window():
    listings = [_listing(salary_min=None, salary_max=30000)]
    assert pipeline.filter_by_salary(listings, 50000, 200000) == []


def test_filter_by_salary_keeps_zero_bound():
    """0 is a stated value, not a missing one — it must not be read as unknown."""
    listings = [_listing(salary_min=0, salary_max=40000)]
    assert pipeline.filter_by_salary(listings, 0, 30000) == listings


# ---------------------------------------------------------------- interleaving


def test_interleave_by_site_alternates_boards():
    listings = [
        _listing("A", job_board="Indeed"),
        _listing("B", job_board="Indeed"),
        _listing("C", job_board="LinkedIn"),
        _listing("D", job_board="LinkedIn"),
    ]
    result = pipeline.interleave_by_site(listings)
    assert [lst.job_board for lst in result] == ["Indeed", "LinkedIn", "Indeed", "LinkedIn"]


def test_interleave_by_site_preserves_order_within_a_board():
    listings = [
        _listing("A1", job_board="Indeed"),
        _listing("A2", job_board="Indeed"),
        _listing("A3", job_board="Indeed"),
        _listing("B1", job_board="LinkedIn"),
    ]
    result = pipeline.interleave_by_site(listings)
    assert [lst.title for lst in result] == ["A1", "B1", "A2", "A3"]


def test_interleave_by_site_single_board_is_unchanged():
    listings = [_listing("A", job_board="Indeed"), _listing("B", job_board="Indeed")]
    assert pipeline.interleave_by_site(listings) == listings


def test_interleave_by_site_empty():
    assert pipeline.interleave_by_site([]) == []


# ------------------------------------------------------------------ apply()


def _params(**kwargs) -> JobSearchParams:
    return JobSearchParams(keywords="AI Engineer", location="Berlin", **kwargs)


def test_apply_reports_fetched_matched_and_shown_counts():
    listings = [
        _listing("Senior AI Engineer", company="A", job_board="Indeed"),
        _listing("Senior ML Engineer", company="B", job_board="Indeed"),
        _listing("Junior AI Engineer", company="C", job_board="Indeed"),
    ]
    result = pipeline.apply(listings, _params(seniority_level=SeniorityLevel.SENIOR), max_jobs=1)
    assert result.fetched == 3
    assert result.matched == 2
    assert len(result.listings) == 1
    assert result.truncated is True


def test_apply_filters_before_truncating():
    """Truncating first would return one listing where two match."""
    listings = [
        _listing("Junior AI Engineer", company="A", job_board="Indeed"),
        _listing("Senior AI Engineer", company="B", job_board="Indeed"),
        _listing("Senior ML Engineer", company="C", job_board="Indeed"),
    ]
    result = pipeline.apply(listings, _params(seniority_level=SeniorityLevel.SENIOR), max_jobs=2)
    assert [lst.title for lst in result.listings] == [
        "Senior AI Engineer",
        "Senior ML Engineer",
    ]
    assert result.truncated is False


def test_apply_without_interleaving_preserves_scraper_order():
    listings = [
        _listing("AI Engineer", company="A", job_board="Indeed"),
        _listing("AI Engineer", company="B", job_board="Indeed"),
        _listing("AI Engineer", company="C", job_board="LinkedIn"),
    ]
    result = pipeline.apply(listings, _params(), max_jobs=10, interleave=False)
    assert [lst.company for lst in result.listings] == ["A", "B", "C"]


def test_apply_interleaves_before_truncating():
    """Truncation without interleaving would return only the first board."""
    listings = [
        _listing("AI Engineer", company="A1", job_board="Indeed"),
        _listing("AI Engineer", company="A2", job_board="Indeed"),
        _listing("AI Engineer", company="B1", job_board="LinkedIn"),
    ]
    result = pipeline.apply(listings, _params(), max_jobs=2, interleave=True)
    assert [lst.job_board for lst in result.listings] == ["Indeed", "LinkedIn"]


def test_apply_on_empty_input():
    result = pipeline.apply([], _params(), max_jobs=10)
    assert result.listings == []
    assert (result.fetched, result.matched) == (0, 0)
    assert result.truncated is False
