"""Shared fixtures for job research tests"""

import pytest
from pathlib import Path

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, WorkType, SeniorityLevel


@pytest.fixture
def sample_job_listing() -> JobListing:
    return JobListing(
        title="Senior AI Engineer",
        company="TechCorp GmbH",
        location="Berlin",
        salary_min=80000,
        salary_max=120000,
        salary_currency="EUR",
        job_board="StepStone",
        job_url="https://www.stepstone.de/jobs/123",
        work_type="Hybrid",
        description="Looking for an experienced AI Engineer",
        posted_date="2026-03-01",
    )


@pytest.fixture
def sample_job_search_params() -> JobSearchParams:
    return JobSearchParams(
        keywords="AI Engineer",
        location="Berlin",
        work_type=WorkType.HYBRID,
        seniority_level=SeniorityLevel.SENIOR,
        salary_minimum=70000,
        salary_maximum=150000,
    )


@pytest.fixture
def tmp_cache_dir(tmp_path: Path) -> Path:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir
