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
    assert analyzer.get_total_count() == 1


def test_add_listings():
    analyzer = JobAnalyzer()
    listings = [
        JobListing(title="A", company="X", location="Berlin"),
        JobListing(title="B", company="Y", location="Munich"),
    ]
    analyzer.add_listings(listings)
    assert analyzer.get_total_count() == 2


def test_get_salary_stats(analyzer_with_listings):
    stats = analyzer_with_listings.get_salary_stats()
    assert stats["count"] == 3
    assert stats["average"] is not None
    assert stats["median"] is not None
    assert stats["min"] <= stats["max"]


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
    assert len(report) > 0
    assert "Test Report" in report
    assert "## Summary" in report
    assert "## Job Listings" in report


def test_generate_csv_report(analyzer_with_listings):
    csv = analyzer_with_listings.generate_csv_report()
    lines = csv.strip().split("\n")
    assert len(lines) == 4  # header + 3 listings
    assert "Title" in lines[0]
    assert "AI Engineer" in lines[1]


def test_generate_csv_report_empty():
    analyzer = JobAnalyzer()
    assert analyzer.generate_csv_report() == ""
