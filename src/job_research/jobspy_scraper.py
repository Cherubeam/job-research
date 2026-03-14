"""Job scraper using python-jobspy (Indeed + LinkedIn, no API key needed)."""

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd
from jobspy import scrape_jobs
from pydantic import ValidationError

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, WorkType
from job_research.utils import create_cache_key, load_cache, save_cache

logger = logging.getLogger(__name__)

_TITLE_STOPWORDS = frozenset({
    "senior", "junior", "lead", "staff", "principal", "head",
    "m/w/d", "f/m/d", "w/m/d", "gn", "d", "m", "f", "w",
    "in", "und", "and", "the", "for", "of", "de", "der", "die", "das",
})

_JOB_TYPE_MAP = {
    "fulltime": "Full-time",
    "parttime": "Part-time",
    "contract": "Contract",
    "internship": "Internship",
}


class JobSpyScraper:
    """Scrapes Indeed + LinkedIn via python-jobspy (no API key needed)."""

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
            "jobspy",
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

        listings = listings[: self._max_jobs]

        if not listings:
            raise RuntimeError(
                "Job search returned no relevant listings. "
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

        search_term = f'"{params.keywords}"'

        kwargs: dict = {
            "site_name": ["indeed", "linkedin"],
            "search_term": search_term,
            "location": location,
            "country_indeed": self._country,
            "results_wanted": self._max_jobs * 2,
            "linkedin_fetch_description": True,
            "verbose": 2,
        }
        if job_type is not None:
            kwargs["job_type"] = job_type
        if is_remote is not None:
            kwargs["is_remote"] = is_remote

        try:
            logger.info(
                "Scraping Indeed+LinkedIn: search_term=%r, location=%r, max=%d",
                search_term,
                location,
                self._max_jobs * 2,
            )
            df = scrape_jobs(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                f"JobSpy scraping failed: {exc}. "
                "This may be a temporary issue — try again in a few minutes."
            ) from exc

        if df.empty:
            logger.info("JobSpy returned 0 results")
            return []

        logger.info("JobSpy returned %d raw results", len(df))
        if "site" in df.columns:
            site_counts = df["site"].value_counts().to_dict()
            logger.info("Results per site: %s", site_counts)

        keyword_tokens = self._build_keyword_tokens(
            params.keywords, params.job_title_alternatives
        )

        listings: list[JobListing] = []
        skipped_irrelevant = 0
        for _, row in df.iterrows():
            listing = self._to_job_listing(row)
            if listing is None:
                continue
            if not self._is_relevant(listing.title, keyword_tokens):
                skipped_irrelevant += 1
                logger.debug("Skipped irrelevant: %s", listing.title)
                continue
            listings.append(listing)

        if skipped_irrelevant:
            logger.info(
                "Filtered %d irrelevant titles, kept %d/%d",
                skipped_irrelevant,
                len(listings),
                len(df),
            )
        else:
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

    @staticmethod
    def _build_keyword_tokens(
        keywords: str, alternatives: list[str]
    ) -> set[str]:
        """Build a set of meaningful tokens from keywords and alternatives."""
        all_text = [keywords] + alternatives
        tokens: set[str] = set()
        for phrase in all_text:
            for word in re.split(r"[\s/,;()\-]+", phrase.lower()):
                word = word.strip()
                if word and word not in _TITLE_STOPWORDS:
                    tokens.add(word)
        return tokens

    @staticmethod
    def _is_relevant(title: str, keyword_tokens: set[str]) -> bool:
        """Check if a job title shares at least one meaningful token with keywords."""
        title_tokens = {
            w.strip()
            for w in re.split(r"[\s/,;()\-]+", title.lower())
            if w.strip() and w.strip() not in _TITLE_STOPWORDS
        }
        return bool(title_tokens & keyword_tokens)

    @staticmethod
    def _map_work_type_from_row(row: pd.Series) -> str:
        """Map jobspy's is_remote and job_type columns to a display string."""
        is_remote = row.get("is_remote")
        if is_remote is True or (isinstance(is_remote, str) and is_remote.lower() == "true"):
            return "Remote"

        job_type = row.get("job_type")
        if job_type and isinstance(job_type, str) and not pd.isna(job_type):
            return _JOB_TYPE_MAP.get(job_type.lower().replace("-", "").replace("_", ""), "")

        return ""

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

        # Map job_board from site column
        site = _safe_str(row.get("site"))
        job_board = site.capitalize() if site else ""

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
                job_board=job_board,
                work_type=self._map_work_type_from_row(row),
            )
        except ValidationError:
            logger.info("Skipped invalid row: %.100s", title)
            return None

    @staticmethod
    def _deduplicate(listings: list[JobListing]) -> list[JobListing]:
        """Remove duplicate listings by URL and by title+company."""
        seen_urls: set[str] = set()
        seen_keys: set[str] = set()
        result: list[JobListing] = []
        for listing in listings:
            # Always check title+company
            key = f"{listing.title.lower()}|{listing.company.lower()}"
            if key in seen_keys:
                continue
            seen_keys.add(key)

            # Also check URL if present
            if listing.job_url and listing.job_url.strip():
                if listing.job_url in seen_urls:
                    continue
                seen_urls.add(listing.job_url)

            result.append(listing)
        return result
