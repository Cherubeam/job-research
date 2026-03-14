"""Tests for IndeedDirectScraper (mocked — no live HTTP)."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, WorkType
from job_research.indeed import IndeedDirectScraper


@pytest.fixture
def sample_jobspy_dataframe() -> pd.DataFrame:
    """Realistic jobspy DataFrame with 4 rows (1 missing title for edge-case testing)."""
    return pd.DataFrame(
        {
            "title": [
                "AI Engineer",
                "Machine Learning Engineer",
                "Data Scientist",
                np.nan,
            ],
            "company": ["TechCorp", "ML Startup GmbH", "DataCo", "Unknown"],
            "location": ["Berlin, Germany", "Munich", "Hamburg", "Frankfurt"],
            "min_amount": [70000, np.nan, 60000, 50000],
            "max_amount": [95000, np.nan, 80000, 70000],
            "job_url": [
                "https://de.indeed.com/viewjob?jk=abc123",
                "https://de.indeed.com/viewjob?jk=def456",
                "https://de.indeed.com/viewjob?jk=ghi789",
                "https://de.indeed.com/viewjob?jk=jkl012",
            ],
            "description": [
                "Looking for an AI engineer with PyTorch experience.",
                "Join our ML team to build recommendation systems.",
                "Analyze and model complex datasets.",
                "Some job description.",
            ],
            "date_posted": ["2026-03-10", "2026-03-09", np.nan, "2026-03-08"],
        }
    )


@pytest.fixture
def scraper() -> IndeedDirectScraper:
    return IndeedDirectScraper(max_jobs=20, country="Germany")


class TestParameterMapping:
    """Tests that search params are correctly mapped to jobspy kwargs."""

    @patch("job_research.indeed.scrape_jobs")
    def test_basic_search_params(
        self, mock_scrape, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI Engineer", location="Berlin")

        scraper._scrape(params)

        mock_scrape.assert_called_once()
        call_kwargs = mock_scrape.call_args[1]
        assert call_kwargs["site_name"] == ["indeed"]
        assert call_kwargs["search_term"] == "AI Engineer"
        assert call_kwargs["location"] == "Berlin"
        assert call_kwargs["country_indeed"] == "Germany"
        assert call_kwargs["results_wanted"] == 20

    @patch("job_research.indeed.scrape_jobs")
    def test_all_of_germany_maps_to_germany(
        self, mock_scrape, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="Python", location="All of Germany")

        scraper._scrape(params)

        assert mock_scrape.call_args[1]["location"] == "Germany"

    @patch("job_research.indeed.scrape_jobs")
    def test_remote_work_type(
        self, mock_scrape, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin", work_type=WorkType.REMOTE)

        scraper._scrape(params)

        call_kwargs = mock_scrape.call_args[1]
        assert call_kwargs["is_remote"] is True
        assert "job_type" not in call_kwargs

    @patch("job_research.indeed.scrape_jobs")
    def test_onsite_work_type(
        self, mock_scrape, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin", work_type=WorkType.ONSITE)

        scraper._scrape(params)

        assert mock_scrape.call_args[1]["is_remote"] is False

    @patch("job_research.indeed.scrape_jobs")
    def test_any_work_type_passes_no_filter(
        self, mock_scrape, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin", work_type=WorkType.ANY)

        scraper._scrape(params)

        call_kwargs = mock_scrape.call_args[1]
        assert "is_remote" not in call_kwargs
        assert "job_type" not in call_kwargs


class TestDataFrameConversion:
    """Tests that DataFrame rows are correctly converted to JobListing objects."""

    def test_full_row_conversion(
        self, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        row = sample_jobspy_dataframe.iloc[0]
        listing = scraper._to_job_listing(row)

        assert listing is not None
        assert listing.title == "AI Engineer"
        assert listing.company == "TechCorp"
        assert listing.location == "Berlin, Germany"
        assert listing.salary_min == 70000
        assert listing.salary_max == 95000
        assert listing.job_url == "https://de.indeed.com/viewjob?jk=abc123"
        assert listing.description == "Looking for an AI engineer with PyTorch experience."
        assert listing.posted_date == "2026-03-10"
        assert listing.job_board == "Indeed"

    def test_missing_salary_becomes_none(
        self, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        row = sample_jobspy_dataframe.iloc[1]
        listing = scraper._to_job_listing(row)

        assert listing is not None
        assert listing.salary_min is None
        assert listing.salary_max is None

    def test_missing_date_becomes_empty_string(
        self, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        row = sample_jobspy_dataframe.iloc[2]
        listing = scraper._to_job_listing(row)

        assert listing is not None
        assert listing.posted_date == ""

    def test_nan_title_returns_none(
        self, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        row = sample_jobspy_dataframe.iloc[3]
        listing = scraper._to_job_listing(row)

        assert listing is None


class TestScrape:
    """Tests the _scrape method end-to-end (mocked jobspy)."""

    @patch("job_research.indeed.scrape_jobs")
    def test_skips_rows_without_title(
        self, mock_scrape, scraper: IndeedDirectScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin")

        listings = scraper._scrape(params)

        # 4 rows, 1 has NaN title → 3 valid listings
        assert len(listings) == 3

    @patch("job_research.indeed.scrape_jobs")
    def test_empty_dataframe_returns_empty_list(
        self, mock_scrape, scraper: IndeedDirectScraper
    ) -> None:
        mock_scrape.return_value = pd.DataFrame()
        params = JobSearchParams(keywords="nonexistent", location="Berlin")

        listings = scraper._scrape(params)

        assert listings == []

    @patch("job_research.indeed.scrape_jobs")
    def test_jobspy_exception_raises_runtime_error(
        self, mock_scrape, scraper: IndeedDirectScraper
    ) -> None:
        mock_scrape.side_effect = Exception("Connection timeout")
        params = JobSearchParams(keywords="AI", location="Berlin")

        with pytest.raises(RuntimeError, match="Indeed scraping failed"):
            scraper._scrape(params)


class TestSearchJobsCache:
    """Tests caching behavior in search_jobs."""

    @patch("job_research.indeed.scrape_jobs")
    def test_cache_miss_triggers_scrape(
        self,
        mock_scrape,
        scraper: IndeedDirectScraper,
        sample_jobspy_dataframe: pd.DataFrame,
        tmp_cache_dir: Path,
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin")

        listings = scraper.search_jobs(params, tmp_cache_dir)

        mock_scrape.assert_called_once()
        assert len(listings) == 3

    @patch("job_research.indeed.scrape_jobs")
    def test_cache_hit_skips_scrape(
        self,
        mock_scrape,
        scraper: IndeedDirectScraper,
        sample_jobspy_dataframe: pd.DataFrame,
        tmp_cache_dir: Path,
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin")

        # First call populates cache
        scraper.search_jobs(params, tmp_cache_dir)
        mock_scrape.reset_mock()

        # Second call should hit cache
        listings = scraper.search_jobs(params, tmp_cache_dir)

        mock_scrape.assert_not_called()
        assert len(listings) == 3

    @patch("job_research.indeed.scrape_jobs")
    def test_empty_results_raise_runtime_error(
        self,
        mock_scrape,
        scraper: IndeedDirectScraper,
        tmp_cache_dir: Path,
    ) -> None:
        mock_scrape.return_value = pd.DataFrame()
        params = JobSearchParams(keywords="nonexistent", location="Berlin")

        with pytest.raises(RuntimeError, match="no job listings"):
            scraper.search_jobs(params, tmp_cache_dir)


class TestDeduplication:
    """Tests the deduplication logic."""

    def test_dedup_by_url(self, scraper: IndeedDirectScraper) -> None:
        listings = [
            JobListing(title="AI Engineer", company="A", job_url="https://example.com/1"),
            JobListing(title="AI Engineer (dup)", company="A", job_url="https://example.com/1"),
            JobListing(title="ML Engineer", company="B", job_url="https://example.com/2"),
        ]

        result = scraper._deduplicate(listings)

        assert len(result) == 2
        assert result[0].title == "AI Engineer"
        assert result[1].title == "ML Engineer"

    def test_dedup_by_title_company_when_no_url(self, scraper: IndeedDirectScraper) -> None:
        listings = [
            JobListing(title="AI Engineer", company="TechCorp"),
            JobListing(title="AI Engineer", company="TechCorp"),
            JobListing(title="AI Engineer", company="OtherCorp"),
        ]

        result = scraper._deduplicate(listings)

        assert len(result) == 2


class TestWorkTypeMapping:
    """Tests _map_work_type edge cases."""

    def test_hybrid_returns_no_filter(self, scraper: IndeedDirectScraper) -> None:
        params = JobSearchParams(work_type=WorkType.HYBRID)
        job_type, is_remote = scraper._map_work_type(params)
        assert job_type is None
        assert is_remote is None

    def test_remote_returns_is_remote_true(self, scraper: IndeedDirectScraper) -> None:
        params = JobSearchParams(work_type=WorkType.REMOTE)
        job_type, is_remote = scraper._map_work_type(params)
        assert job_type is None
        assert is_remote is True

    def test_onsite_returns_is_remote_false(self, scraper: IndeedDirectScraper) -> None:
        params = JobSearchParams(work_type=WorkType.ONSITE)
        job_type, is_remote = scraper._map_work_type(params)
        assert is_remote is False
