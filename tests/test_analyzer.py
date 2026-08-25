"""Tests for analyzer.py"""

import pytest

from job_research.analyzer import JobAnalyzer, JobListing


@pytest.fixture
def analyzer_with_listings() -> JobAnalyzer:
    analyzer = JobAnalyzer()
    analyzer.add_listings([
        JobListing(title="AI Engineer", company="Alpha GmbH", location="Berlin",
                   salary_min=80000, salary_max=120000, job_board="StepStone", work_type="Hybrid"),
        JobListing(title="ML Engineer", company="Beta AG", location="Munich",
                   salary_min=70000, salary_max=100000, job_board="LinkedIn", work_type="Remote"),
        JobListing(title="Data Scientist", company="Gamma SE", location="Berlin",
                   salary_min=75000, salary_max=110000, job_board="StepStone", work_type="Onsite"),
    ])
    return analyzer


def test_add_listing():
    analyzer = JobAnalyzer()
    listing = JobListing(title="Engineer", company="Co", location="Berlin")
    analyzer.add_listing(listing)
    assert analyzer.listings == [listing]


def test_add_listings_preserves_order():
    analyzer = JobAnalyzer()
    first = JobListing(title="A", company="X", location="Berlin")
    second = JobListing(title="B", company="Y", location="Munich")
    analyzer.add_listings([first, second])
    assert analyzer.listings == [first, second]


def test_get_salary_stats(analyzer_with_listings):
    # Midpoints: 100000, 85000, 92500 -> mean 92500, median 92500
    stats = analyzer_with_listings.get_salary_stats()
    assert stats == {
        "count": 3,
        "average": 92500.0,
        "median": 92500.0,
        "min": 85000.0,
        "max": 100000.0,
    }


def test_get_salary_stats_ignores_listings_without_both_bounds():
    analyzer = JobAnalyzer()
    analyzer.add_listings([
        JobListing(title="A", salary_min=60000, salary_max=80000),
        JobListing(title="B", salary_min=60000),  # max missing -> excluded
        JobListing(title="C"),                    # both missing -> excluded
    ])
    stats = analyzer.get_salary_stats()
    assert stats["count"] == 1
    assert stats["average"] == 70000.0


def test_get_salary_stats_empty():
    analyzer = JobAnalyzer()
    stats = analyzer.get_salary_stats()
    assert stats["count"] == 0
    assert stats["average"] is None


def test_get_listings_by_board(analyzer_with_listings):
    board_counts = analyzer_with_listings.get_listings_by_board()
    assert board_counts["StepStone"] == 2
    assert board_counts["LinkedIn"] == 1


def test_generate_markdown_report(analyzer_with_listings):
    report = analyzer_with_listings.generate_markdown_report("Test Report")
    assert report.startswith("# Test Report\n")
    assert "- **Total Listings:** 3\n" in report
    assert "- **Average Salary:** \u20ac92,500\n" in report
    assert "- **Salary Range:** \u20ac85,000 - \u20ac100,000\n" in report
    # Boards sorted by count, descending
    assert report.index("**StepStone:** 2") < report.index("**LinkedIn:** 1")
    # Every listing rendered, numbered, with its salary and link-free fields
    assert "### 1. AI Engineer\n" in report
    assert "### 2. ML Engineer\n" in report
    assert "### 3. Data Scientist\n" in report
    assert "**Salary:** \u20ac80,000 - \u20ac120,000\n" in report


def test_generate_markdown_report_omits_salary_line_when_absent():
    analyzer = JobAnalyzer()
    analyzer.add_listing(JobListing(title="No Salary Job", company="Co"))
    report = analyzer.generate_markdown_report()
    assert "### 1. No Salary Job\n" in report
    assert "**Salary:**" not in report
    assert "- **Average Salary:**" not in report


def test_generate_csv_report(analyzer_with_listings):
    csv = analyzer_with_listings.generate_csv_report()
    lines = csv.strip().split("\n")
    assert len(lines) == 4  # header + 3 listings
    assert "Title" in lines[0]
    assert "AI Engineer" in lines[1]


def test_generate_csv_report_empty():
    analyzer = JobAnalyzer()
    assert analyzer.generate_csv_report() == ""
