"""Indeed scraper using python-jobspy (mobile API, no API key needed)."""

import logging
from pathlib import Path
from typing import Optional

import pandas as pd
from jobspy import scrape_jobs
from pydantic import ValidationError

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, WorkType
from job_research.utils import create_cache_key, load_cache, save_cache

logger = logging.getLogger(__name__)


class IndeedDirectScraper:
    """Scrapes Indeed via python-jobspy (mobile API, no API key needed)."""

    def __init__(self, max_jobs: int = 20, country: str = "Germany") -> None:
        self._max_jobs = max_jobs
        self._country = country

    def search_jobs(
        self,
        params: JobSearchParams,
        cache_dir: Path,
        cache_duration_hours: int = 24,
    ) -> list[JobListing]:
        """Search for jobs matching *params*, using a local cache."""
        cache_key = create_cache_key(
            "indeed_direct",
            params.keywords,
            params.location,
            work_type=params.work_type.value,
            seniority_level=params.seniority_level.value,
            salary_min=params.salary_minimum,
            salary_max=params.salary_maximum,
        )
        cached = load_cache(cache_dir, cache_key)
        if cached is not None:
            logger.info("Cache hit for key %s", cache_key)
            return [JobListing(**item) for item in cached]

        listings = self._scrape(params)

        before_dedup = len(listings)
        listings = self._deduplicate(listings)
        if before_dedup != len(listings):
            logger.info("Dedup removed %d duplicates", before_dedup - len(listings))

        if not listings:
            raise RuntimeError(
                "Indeed search returned no job listings. "
                "Try broadening your search keywords or location."
            )

        save_cache(
            cache_dir,
            cache_key,
            [lst.model_dump() for lst in listings],
            cache_duration_hours,
        )
        logger.info("Found %d listings (saved to cache)", len(listings))
        return listings

    def _scrape(self, params: JobSearchParams) -> list[JobListing]:
        """Call jobspy and convert results to JobListing objects."""
        location = params.location if params.location != "All of Germany" else "Germany"
        job_type, is_remote = self._map_work_type(params)

        kwargs: dict = {
            "site_name": ["indeed"],
            "search_term": params.keywords,
            "location": location,
            "country_indeed": self._country,
            "results_wanted": self._max_jobs,
        }
        if job_type is not None:
            kwargs["job_type"] = job_type
        if is_remote is not None:
            kwargs["is_remote"] = is_remote

        try:
            logger.info(
                "Scraping Indeed: keywords=%r, location=%r, max=%d",
                params.keywords,
                location,
                self._max_jobs,
            )
            df = scrape_jobs(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"Indeed scraping failed: {exc}. "
                "This may be a temporary issue — try again in a few minutes."
            ) from exc

        if df.empty:
            logger.info("Indeed returned 0 results")
            return []

        logger.info("Indeed returned %d raw results", len(df))
        listings: list[JobListing] = []
        for _, row in df.iterrows():
            listing = self._to_job_listing(row)
            if listing is not None:
                listings.append(listing)

        logger.info("Converted %d/%d rows to JobListing", len(listings), len(df))
        return listings

    def _map_work_type(
        self, params: JobSearchParams
    ) -> tuple[Optional[str], Optional[bool]]:
        """Map WorkType enum to jobspy's job_type and is_remote parameters."""
        if params.work_type == WorkType.REMOTE:
            return None, True
        if params.work_type == WorkType.ONSITE:
            return None, False
        # HYBRID and ANY — don't restrict
        return None, None

    def _to_job_listing(self, row: pd.Series) -> Optional[JobListing]:
        """Convert a jobspy DataFrame row to a JobListing, or None on failure."""
        title = row.get("title")
        if not title or (isinstance(title, float) and pd.isna(title)):
            return None

        def _safe_str(val: object) -> str:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return ""
            return str(val)

        def _safe_int(val: object) -> Optional[int]:
            if val is None or (isinstance(val, float) and pd.isna(val)):
                return None
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return None

        try:
            return JobListing(
                title=str(title),
                company=_safe_str(row.get("company")),
                location=_safe_str(row.get("location")),
                salary_min=_safe_int(row.get("min_amount")),
                salary_max=_safe_int(row.get("max_amount")),
                job_url=_safe_str(row.get("job_url")),
                description=_safe_str(row.get("description")),
                posted_date=_safe_str(row.get("date_posted")),
                job_board="Indeed",
            )
        except ValidationError:
            logger.info("Skipped invalid row: %.100s", title)
            return None

    @staticmethod
    def _deduplicate(listings: list[JobListing]) -> list[JobListing]:
        """Remove duplicate listings by URL, then by title+company."""
        seen_urls: set[str] = set()
        seen_keys: set[str] = set()
        result: list[JobListing] = []
        for listing in listings:
            if listing.job_url and listing.job_url.strip():
                if listing.job_url in seen_urls:
                    continue
                seen_urls.add(listing.job_url)
            else:
                key = f"{listing.title.lower()}|{listing.company.lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            result.append(listing)
        return result
