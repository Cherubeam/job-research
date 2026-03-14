"""Tests for scraper.py"""

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from job_research.analyzer import JobListing
from job_research.config import JobBoardConfig, JobSearchParams, WorkType
from job_research.scraper import ClaudeScraper


@pytest.fixture
def scraper() -> ClaudeScraper:
    with patch("job_research.scraper.anthropic.Anthropic"):
        return ClaudeScraper(api_key="sk-test", model="claude-haiku-4-5-20251001", max_jobs=10)


# ----------------------------------------------------------------- salary norm

@pytest.mark.parametrize("salary_str,expected", [
    ("€80.000 – 120.000", (80000, 120000)),
    ("70k-100k", (70000, 100000)),
    ("ab 80000 EUR", (80000, None)),
    ("", (None, None)),
    ("  ", (None, None)),
])
def test_normalize_salary(scraper, salary_str, expected):
    assert scraper._normalize_salary(salary_str) == expected


def test_normalize_salary_none(scraper):
    assert scraper._normalize_salary(None) == (None, None)  # type: ignore[arg-type]


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


# ------------------------------------------------------------- listing_from_dict

def test_listing_from_dict_valid(scraper):
    data = {
        "title": "Senior AI Engineer",
        "company": "TechCorp",
        "location": "Berlin",
        "salary_min": 80000,
        "salary_max": 120000,
        "work_type": "Hybrid",
        "job_board": "StepStone",
        "job_url": "https://stepstone.de/1",
    }
    listing = scraper._listing_from_dict(data)
    assert listing is not None
    assert listing.title == "Senior AI Engineer"
    assert listing.salary_min == 80000
    assert listing.salary_max == 120000


def test_listing_from_dict_missing_title(scraper):
    data = {"company": "TechCorp", "location": "Berlin"}
    assert scraper._listing_from_dict(data) is None


def test_listing_from_dict_null_salary(scraper):
    data = {"title": "Engineer", "company": "Co", "location": "Berlin",
            "salary_min": None, "salary_max": None}
    listing = scraper._listing_from_dict(data)
    assert listing is not None
    assert listing.salary_min is None
    assert listing.salary_max is None


# ---------------------------------------------------------- build_search_query

def test_build_search_query_contains_keywords(scraper, sample_job_search_params):
    query = scraper._build_search_query(sample_job_search_params)
    assert "AI Engineer" in query
    assert "Berlin" in query


def test_build_search_query_contains_job_boards(scraper, sample_job_search_params):
    query = scraper._build_search_query(sample_job_search_params)
    assert "stepstone.de" in query
    assert "linkedin.com" in query
    assert "arbeitsagentur.de" in query


def test_disabled_board_excluded_from_query(sample_job_search_params):
    board_config = JobBoardConfig(search_stepstone=False)
    with patch("job_research.scraper.anthropic.Anthropic"):
        s = ClaudeScraper(api_key="sk-test", model="claude-haiku-4-5-20251001", board_config=board_config)
    query = s._build_search_query(sample_job_search_params)
    assert "stepstone.de" not in query
    assert "linkedin.com" in query


# ---------------------------------------------------------- API call (mocked)

def test_make_api_call_retries_on_error(scraper):
    import anthropic as anthropic_module

    mock_client = MagicMock()
    scraper._client = mock_client

    error = anthropic_module.APIStatusError(
        "rate limit", response=MagicMock(status_code=429), body={}
    )
    success_response = MagicMock()
    success_response.content = []
    mock_client.messages.create.side_effect = [error, success_response]

    with patch("job_research.scraper.time.sleep"):
        result = scraper._make_api_call([{"role": "user", "content": "test"}])

    assert mock_client.messages.create.call_count == 2
    assert result is success_response


def test_search_jobs_returns_empty_list_on_exception(scraper, sample_job_search_params, tmp_cache_dir):
    scraper._client = MagicMock(side_effect=Exception("boom"))
    result = scraper.search_jobs(sample_job_search_params, tmp_cache_dir)
    assert result == []
