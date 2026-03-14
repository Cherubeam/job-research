"""Tests for JobSpyScraper (mocked — no live HTTP)."""

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, WorkType
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
        assert call_kwargs["site_name"] == ["indeed", "linkedin"]
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

        assert mock_scrape.call_args[1]["site_name"] == ["indeed", "linkedin"]

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_overfetch_requests_double(
        self, mock_scrape, scraper: JobSpyScraper, sample_jobspy_dataframe: pd.DataFrame
    ) -> None:
        mock_scrape.return_value = sample_jobspy_dataframe
        params = JobSearchParams(keywords="AI", location="Berlin")

        scraper._scrape(params)

        assert mock_scrape.call_args[1]["results_wanted"] == 40  # 20 * 2

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


class TestRelevanceFiltering:
    """Tests title relevance filtering."""

    def test_relevant_title_matches(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens(
            "AI Engineer", ["Machine Learning Engineer"]
        )
        assert JobSpyScraper._is_relevant("Senior AI Engineer (m/w/d)", tokens)

    def test_irrelevant_title_rejected(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens(
            "AI Engineer", ["Machine Learning Engineer"]
        )
        assert not JobSpyScraper._is_relevant(
            "Shopify API GraphQL - Senior Backend Developer", tokens
        )

    def test_alternative_title_matches(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens(
            "AI Engineer", ["Machine Learning Engineer", "Deep Learning Engineer"]
        )
        assert JobSpyScraper._is_relevant("Deep Learning Researcher", tokens)

    def test_case_insensitive(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens("AI Engineer", [])
        assert JobSpyScraper._is_relevant("ai engineer", tokens)

    def test_stopword_only_title_rejected(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens("Senior Engineer", [])
        # "Senior" is a stopword, so only "engineer" is a keyword token
        assert JobSpyScraper._is_relevant("Software Engineer", tokens)
        assert not JobSpyScraper._is_relevant("Senior Manager", tokens)

    def test_data_scientist_matches_data(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens(
            "AI Engineer", ["Data Scientist"]
        )
        assert JobSpyScraper._is_relevant("Data Scientist", tokens)

    @patch("job_research.jobspy_scraper.scrape_jobs")
    def test_filters_irrelevant_titles_in_scrape(
        self, mock_scrape, scraper: JobSpyScraper
    ) -> None:
        df = pd.DataFrame(
            {
                "site": ["indeed", "indeed", "indeed"],
                "title": ["AI Engineer", "Shopify Backend Developer", "ML Engineer"],
                "company": ["A", "B", "C"],
                "location": ["Berlin", "Berlin", "Berlin"],
                "min_amount": [np.nan, np.nan, np.nan],
                "max_amount": [np.nan, np.nan, np.nan],
                "job_url": ["https://a.com/1", "https://b.com/2", "https://c.com/3"],
                "description": ["d1", "d2", "d3"],
                "date_posted": [np.nan, np.nan, np.nan],
                "is_remote": [False, False, False],
                "job_type": [np.nan, np.nan, np.nan],
            }
        )
        mock_scrape.return_value = df
        params = JobSearchParams(
            keywords="AI Engineer",
            location="Berlin",
            job_title_alternatives=["ML Engineer"],
        )

        listings = scraper._scrape(params)

        titles = [lst.title for lst in listings]
        assert "AI Engineer" in titles
        assert "ML Engineer" in titles
        assert "Shopify Backend Developer" not in titles


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
    def test_empty_dataframe_returns_empty_list(
        self, mock_scrape, scraper: JobSpyScraper
    ) -> None:
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
    def test_overfetch_truncates_to_max_jobs(
        self,
        mock_scrape,
        tmp_cache_dir: Path,
    ) -> None:
        small_scraper = JobSpyScraper(max_jobs=2, country="Germany")
        # Create a DataFrame with 5 relevant rows
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

        assert len(listings) == 2


class TestDeduplication:
    """Tests the deduplication logic."""

    def test_dedup_by_url(self, scraper: JobSpyScraper) -> None:
        listings = [
            JobListing(title="AI Engineer", company="A", job_url="https://example.com/1"),
            JobListing(title="AI Engineer v2", company="B", job_url="https://example.com/1"),
            JobListing(title="ML Engineer", company="C", job_url="https://example.com/2"),
        ]

        result = scraper._deduplicate(listings)

        assert len(result) == 2

    def test_dedup_same_title_company_different_urls(self, scraper: JobSpyScraper) -> None:
        """Amazon-style: same job posted in different locations with different URLs."""
        listings = [
            JobListing(
                title="2026 Software Dev Engineer Intern",
                company="Amazon",
                job_url="https://indeed.com/viewjob?jk=aaa",
                location="Berlin",
            ),
            JobListing(
                title="2026 Software Dev Engineer Intern",
                company="Amazon",
                job_url="https://indeed.com/viewjob?jk=bbb",
                location="Munich",
            ),
            JobListing(
                title="2026 Software Dev Engineer Intern",
                company="Amazon",
                job_url="https://indeed.com/viewjob?jk=ccc",
                location="Dresden",
            ),
            JobListing(
                title="ML Engineer",
                company="Other Corp",
                job_url="https://indeed.com/viewjob?jk=ddd",
            ),
        ]

        result = scraper._deduplicate(listings)

        assert len(result) == 2
        assert result[0].title == "2026 Software Dev Engineer Intern"
        assert result[1].title == "ML Engineer"

    def test_dedup_by_title_company_when_no_url(self, scraper: JobSpyScraper) -> None:
        listings = [
            JobListing(title="AI Engineer", company="TechCorp"),
            JobListing(title="AI Engineer", company="TechCorp"),
            JobListing(title="AI Engineer", company="OtherCorp"),
        ]

        result = scraper._deduplicate(listings)

        assert len(result) == 2


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


class TestBuildKeywordTokens:
    """Tests keyword tokenization."""

    def test_basic_tokenization(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens("AI Engineer", [])
        assert "ai" in tokens
        assert "engineer" in tokens

    def test_includes_alternatives(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens(
            "AI Engineer", ["Machine Learning Engineer"]
        )
        assert "machine" in tokens
        assert "learning" in tokens

    def test_excludes_stopwords(self) -> None:
        tokens = JobSpyScraper._build_keyword_tokens("Senior AI Engineer", [])
        assert "senior" not in tokens
        assert "ai" in tokens
