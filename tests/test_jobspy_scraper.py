"""Tests for JobSpyScraper (mocked — no live HTTP)."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from job_research.config import JobSearchParams, SeniorityLevel, WorkType
from job_research.jobspy_scraper import JobSpyScraper


@pytest.fixture
def sample_jobspy_dataframe() -> pd.DataFrame:
    """Realistic jobspy DataFrame with 5 rows including edge cases."""
    return pd.DataFrame(
        {
            "site": ["indeed", "linkedin", "indeed", "indeed", "linkedin"],
            "title": [
                "AI Engineer",
                "Machine Learning Engineer",
                "Data Scientist",
                np.nan,
                "Senior AI Researcher",
            ],
            "company": ["TechCorp", "ML Startup GmbH", "DataCo", "Unknown", "DeepTech"],
            "location": ["Berlin, Germany", "Munich", "Hamburg", "Frankfurt", "Berlin"],
            "min_amount": [70000, np.nan, 60000, 50000, 90000],
            "max_amount": [95000, np.nan, 80000, 70000, 130000],
            "job_url": [
                "https://de.indeed.com/viewjob?jk=abc123",
                "https://linkedin.com/jobs/view/def456",
                "https://de.indeed.com/viewjob?jk=ghi789",
                "https://de.indeed.com/viewjob?jk=jkl012",
                "https://linkedin.com/jobs/view/mno345",
            ],
            "description": [
                "Looking for an AI engineer with PyTorch experience.",
                "Join our ML team to build recommendation systems.",
                "Analyze and model complex datasets.",
                "Some job description.",
                "Leading AI research team.",
            ],
            "date_posted": ["2026-03-10", "2026-03-09", np.nan, "2026-03-08", "2026-03-07"],
            "is_remote": [False, True, False, False, np.nan],
            "job_type": ["fulltime", np.nan, "contract", "internship", "fulltime"],
        }
    )


@pytest.fixture
def scraper() -> JobSpyScraper:
    return JobSpyScraper(max_jobs=20, country="Germany")


class TestParameterMapping:
    """Tests that search params are correctly mapped to jobspy kwargs."""

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_basic_search_params(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI Engineer", location="Berlin")

        scraper._scrape(params)

        mock_scrape.assert_called_once()
        call_kwargs = mock_scrape.call_args[1]
        assert call_kwargs["site_name"] == ["linkedin", "indeed"]
        assert call_kwargs["search_term"] == '"AI Engineer"'
        assert call_kwargs["location"] == "Berlin"
        assert call_kwargs["country_indeed"] == "Germany"
        assert call_kwargs["linkedin_fetch_description"] is True
        assert call_kwargs["verbose"] == 2

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_site_name_includes_linkedin(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin")

        scraper._scrape(params)

        assert mock_scrape.call_args[1]["site_name"] == ["linkedin", "indeed"]

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_overfetch_requests_1_5x(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin")

        scraper._scrape(params)

        assert mock_scrape.call_args[1]["results_wanted"] == 30  # int(20 * 1.5)

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_all_of_germany_maps_to_germany(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="Python", location="All of Germany")

        scraper._scrape(params)

        assert mock_scrape.call_args[1]["location"] == "Germany"

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_remote_work_type(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin", work_type=WorkType.REMOTE)

        scraper._scrape(params)

        call_kwargs = mock_scrape.call_args[1]
        assert call_kwargs["is_remote"] is True
        assert "job_type" not in call_kwargs

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_onsite_work_type(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin", work_type=WorkType.ONSITE)

        scraper._scrape(params)

        assert mock_scrape.call_args[1]["is_remote"] is False

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_any_work_type_passes_no_filter(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
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
        self, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
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

    def test_job_board_from_site_column(
        self, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        indeed_row = sample_jobspy_dataframe.iloc[0]
        linkedin_row = sample_jobspy_dataframe.iloc[1]

        assert scraper._to_job_listing(indeed_row).job_board == "Indeed"
        assert scraper._to_job_listing(linkedin_row).job_board == "Linkedin"

    def test_missing_salary_becomes_none(
        self, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        row = sample_jobspy_dataframe.iloc[1]
        listing = scraper._to_job_listing(row)

        assert listing is not None
        assert listing.salary_min is None
        assert listing.salary_max is None

    def test_missing_date_becomes_empty_string(
        self, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        row = sample_jobspy_dataframe.iloc[2]
        listing = scraper._to_job_listing(row)

        assert listing is not None
        assert listing.posted_date == ""

    def test_nan_title_returns_none(
        self, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        row = sample_jobspy_dataframe.iloc[3]
        listing = scraper._to_job_listing(row)

        assert listing is None


class TestWorkTypeFromRow:
    """Tests mapping of is_remote and job_type to work_type."""

    def test_maps_is_remote_to_work_type(self, scraper: JobSpyScraper) -> None:
        row = pd.Series({"is_remote": True, "job_type": "fulltime"})
        assert scraper._map_work_type_from_row(row) == "Remote"

    def test_maps_fulltime_job_type(self, scraper: JobSpyScraper) -> None:
        row = pd.Series({"is_remote": False, "job_type": "fulltime"})
        assert scraper._map_work_type_from_row(row) == "Full-time"

    def test_maps_parttime_job_type(self, scraper: JobSpyScraper) -> None:
        row = pd.Series({"is_remote": False, "job_type": "parttime"})
        assert scraper._map_work_type_from_row(row) == "Part-time"

    def test_maps_contract_job_type(self, scraper: JobSpyScraper) -> None:
        row = pd.Series({"is_remote": False, "job_type": "contract"})
        assert scraper._map_work_type_from_row(row) == "Contract"

    def test_maps_internship_job_type(self, scraper: JobSpyScraper) -> None:
        row = pd.Series({"is_remote": False, "job_type": "internship"})
        assert scraper._map_work_type_from_row(row) == "Internship"

    def test_nan_is_remote_falls_through_to_job_type(self, scraper: JobSpyScraper) -> None:
        row = pd.Series({"is_remote": np.nan, "job_type": "contract"})
        assert scraper._map_work_type_from_row(row) == "Contract"

    def test_missing_both_returns_empty(self, scraper: JobSpyScraper) -> None:
        row = pd.Series({"is_remote": np.nan, "job_type": np.nan})
        assert scraper._map_work_type_from_row(row) == ""


class TestScrape:
    """Tests the _scrape method end-to-end (mocked jobspy)."""

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_skips_rows_without_title(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(
            keywords="AI Engineer",
            location="Berlin",
            job_title_alternatives=["Machine Learning Engineer", "Data Scientist", "AI Researcher"],
        )

        listings = scraper._scrape(params)

        # 5 rows: 1 NaN title → 4 valid, all relevant with the alternatives
        assert len(listings) == 4

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_empty_dataframe_returns_empty_list(self, mock_scrape, scraper: JobSpyScraper) -> None:
        mock_scrape.return_value = pd.DataFrame()
        params = JobSearchParams(keywords="nonexistent", location="Berlin")

        listings = scraper._scrape(params)

        assert listings == []

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_jobspy_exception_raises_runtime_error(
        self, mock_scrape, scraper: JobSpyScraper
    ) -> None:
        mock_scrape.side_effect = Exception("Connection timeout")
        params = JobSearchParams(keywords="AI", location="Berlin")

        with pytest.raises(RuntimeError, match="JobSpy scraping failed"):
            scraper._scrape(params)


class TestSearchJobsCache:
    """Tests caching behavior in search_jobs."""

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_cache_miss_triggers_scrape(
        self,
        mock_scrape,
        scraper: JobSpyScraper,
        sample_jobspy_dataframe: pd.DataFrame,
        tmp_cache_dir: Path,
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(
            keywords="AI Engineer",
            location="Berlin",
            job_title_alternatives=["Machine Learning Engineer", "Data Scientist", "AI Researcher"],
        )

        listings = scraper.search_jobs(params, tmp_cache_dir)

        mock_scrape.assert_called_once()
        assert len(listings) > 0

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_cache_hit_skips_scrape(
        self,
        mock_scrape,
        scraper: JobSpyScraper,
        sample_jobspy_dataframe: pd.DataFrame,
        tmp_cache_dir: Path,
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(
            keywords="AI Engineer",
            location="Berlin",
            job_title_alternatives=["Machine Learning Engineer", "Data Scientist", "AI Researcher"],
        )

        scraper.search_jobs(params, tmp_cache_dir)
        mock_scrape.reset_mock()

        listings = scraper.search_jobs(params, tmp_cache_dir)

        mock_scrape.assert_not_called()
        assert len(listings) > 0

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_empty_results_raise_runtime_error(
        self,
        mock_scrape,
        scraper: JobSpyScraper,
        tmp_cache_dir: Path,
    ) -> None:
        mock_scrape.return_value = pd.DataFrame()
        params = JobSearchParams(keywords="nonexistent", location="Berlin")

        with pytest.raises(RuntimeError, match="no relevant listings"):
            scraper.search_jobs(params, tmp_cache_dir)

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_returns_full_fetch_without_truncating(
        self,
        mock_scrape,
        tmp_cache_dir: Path,
    ) -> None:
        """Truncation is the pipeline's job — the scraper caches everything it found."""
        small_scraper = JobSpyScraper(max_jobs=2, country="Germany")
        df = pd.DataFrame(
            {
                "site": ["indeed"] * 5,
                "title": [f"AI Engineer {i}" for i in range(5)],
                "company": [f"Company{i}" for i in range(5)],
                "location": ["Berlin"] * 5,
                "min_amount": [np.nan] * 5,
                "max_amount": [np.nan] * 5,
                "job_url": [f"https://example.com/{i}" for i in range(5)],
                "description": ["desc"] * 5,
                "date_posted": [np.nan] * 5,
                "is_remote": [False] * 5,
                "job_type": [np.nan] * 5,
            }
        )
        mock_scrape.return_value = df
        params = JobSearchParams(keywords="AI Engineer", location="Berlin")

        listings = small_scraper.search_jobs(params, tmp_cache_dir)

        assert len(listings) == 5

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_cache_key_ignores_locally_applied_filters(
        self,
        mock_scrape,
        scraper: JobSpyScraper,
        sample_jobspy_dataframe: pd.DataFrame,
        tmp_cache_dir: Path,
    ) -> None:
        """Salary and seniority are applied after the fetch, so they must not re-fetch."""
        mock_scrape.return_value = sample_jobspy_dataframe
        base = JobSearchParams(keywords="AI Engineer", location="Berlin")
        scraper.search_jobs(base, tmp_cache_dir)

        widened = JobSearchParams(
            keywords="AI Engineer",
            location="Berlin",
            salary_minimum=90000,
            salary_maximum=180000,
            seniority_level=SeniorityLevel.SENIOR,
        )
        scraper.search_jobs(widened, tmp_cache_dir)

        mock_scrape.assert_called_once()  # second search served from cache

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_cache_key_reflects_result_count(
        self,
        mock_scrape,
        sample_jobspy_dataframe: pd.DataFrame,
        tmp_cache_dir: Path,
    ) -> None:
        """Asking for more jobs must re-fetch, not replay the smaller cached set."""
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI Engineer", location="Berlin")

        JobSpyScraper(max_jobs=20).search_jobs(params, tmp_cache_dir)
        JobSpyScraper(max_jobs=200).search_jobs(params, tmp_cache_dir)

        assert mock_scrape.call_count == 2


class TestWorkTypeMapping:
    """Tests _map_work_type edge cases."""

    def test_hybrid_returns_no_filter(self, scraper: JobSpyScraper) -> None:
        params = JobSearchParams(work_type=WorkType.HYBRID)
        job_type, is_remote = scraper._map_work_type(params)
        assert job_type is None
        assert is_remote is None

    def test_remote_returns_is_remote_true(self, scraper: JobSpyScraper) -> None:
        params = JobSearchParams(work_type=WorkType.REMOTE)
        job_type, is_remote = scraper._map_work_type(params)
        assert job_type is None
        assert is_remote is True

    def test_onsite_returns_is_remote_false(self, scraper: JobSpyScraper) -> None:
        params = JobSearchParams(work_type=WorkType.ONSITE)
        job_type, is_remote = scraper._map_work_type(params)
        assert is_remote is False
