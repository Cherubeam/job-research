"""Tests for scraper.py"""

import pytest
from unittest.mock import MagicMock, patch

from job_research.analyzer import JobListing
from job_research.config import JobBoardConfig
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


def test_search_jobs_raises_on_exception(scraper, sample_job_search_params, tmp_cache_dir):
    scraper._client.messages.create = MagicMock(side_effect=Exception("boom"))
    with pytest.raises(Exception, match="boom"):
        scraper.search_jobs(sample_job_search_params, tmp_cache_dir)


# ---------------------------------------------------------- empty-result caching

def test_empty_results_are_not_cached(scraper, sample_job_search_params, tmp_cache_dir):
    """When search returns no listings, save_cache must NOT be called."""
    with patch("job_research.scraper.anthropic.Anthropic"):
        with patch.object(scraper, "_claude_web_search", return_value="no jobs found"):
            with patch.object(scraper, "_parse_results", return_value=[]):
                with patch("job_research.scraper.save_cache") as mock_save:
                    result = scraper.search_jobs(sample_job_search_params, tmp_cache_dir)

    assert result == []
    mock_save.assert_not_called()


# ------------------------------------------------- error surfacing from scraper

def test_claude_web_search_raises_on_no_text_blocks(scraper):
    """_claude_web_search must raise RuntimeError when response has no text blocks."""
    mock_response = MagicMock()
    # Simulate response with only tool-use blocks (no text blocks)
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    mock_response.content = [tool_block]
    scraper._client.messages.create.return_value = mock_response

    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="no text content"):
            scraper._claude_web_search("test query")


def test_claude_web_search_raises_on_empty_text(scraper):
    """_claude_web_search must raise RuntimeError when text blocks are empty."""
    mock_response = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "   "
    mock_response.content = [text_block]
    scraper._client.messages.create.return_value = mock_response

    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="no text content"):
            scraper._claude_web_search("test query")


def test_parse_results_raises_on_invalid_json(scraper, sample_job_search_params):
    """_parse_results must raise RuntimeError on unparseable JSON."""
    mock_response = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = "this is not json at all"
    mock_response.content = [text_block]
    scraper._client.messages.create.return_value = mock_response

    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="Failed to parse job listings"):
            scraper._parse_results("some raw response", sample_job_search_params)


def test_parse_results_raises_on_non_array_json(scraper, sample_job_search_params):
    """_parse_results must raise RuntimeError when JSON is not an array."""
    mock_response = MagicMock()
    text_block = MagicMock()
    text_block.type = "text"
    text_block.text = '{"not": "an array"}'
    mock_response.content = [text_block]
    scraper._client.messages.create.return_value = mock_response

    with patch("job_research.scraper.time.sleep"):
        with pytest.raises(RuntimeError, match="Expected JSON array"):
            scraper._parse_results("some raw response", sample_job_search_params)
