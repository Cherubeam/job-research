"""Post-fetch processing shared by every scraper backend.

Scrapers fetch and normalize; this package decides what the user actually sees.
Keeping the two apart means a rule written once applies to every backend, and
that the cache can hold the raw fetch while the view varies freely on top of it.

Order matters:

1. **relevance** — drop titles that do not match the query, before anything
   downstream spends effort on them.
2. **dedup** — collapse the same posting reached through several sources.
3. **salary / recency / seniority** — narrow to what was asked for.
4. **interleave** — round-robin across boards.
5. **truncate** — cut to `max_jobs`, last, so filtering never returns fewer
   results than requested for no reason.
"""

import logging
from dataclasses import dataclass

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams
from job_research.pipeline.dedup import deduplicate, identity, normalize_location
from job_research.pipeline.filters import (
    filter_by_posted_within,
    filter_by_salary,
    filter_by_seniority,
    infer_seniority,
)
from job_research.pipeline.interleave import interleave_by_site
from job_research.pipeline.relevance import (
    DEFAULT_THRESHOLD,
    filter_by_relevance,
    is_excluded,
    score_title,
)

logger = logging.getLogger(__name__)

__all__ = [
    "DEFAULT_THRESHOLD",
    "PipelineResult",
    "apply",
    "deduplicate",
    "filter_by_posted_within",
    "filter_by_relevance",
    "filter_by_salary",
    "filter_by_seniority",
    "identity",
    "infer_seniority",
    "interleave_by_site",
    "is_excluded",
    "normalize_location",
    "score_title",
]


@dataclass(frozen=True)
class PipelineResult:
    """Listings to display, plus the counts needed to explain what happened."""

    listings: list[JobListing]
    fetched: int
    """Listings the scrapers returned, before any filtering."""
    matched: int
    """Listings that survived filtering, before truncation to `max_jobs`."""

    @property
    def truncated(self) -> bool:
        return self.matched > len(self.listings)


def _log_drop(stage: str, before: int, after: int) -> None:
    if before != after:
        logger.info("%s removed %d listings (%d -> %d)", stage, before - after, before, after)


def apply(
    listings: list[JobListing],
    params: JobSearchParams,
    *,
    max_jobs: int,
    interleave: bool = True,
) -> PipelineResult:
    """Filter, deduplicate, interleave, and truncate raw scraper output."""
    fetched = len(listings)

    before = len(listings)
    listings = filter_by_relevance(
        listings,
        params.keywords,
        params.job_title_alternatives,
        threshold=params.relevance_threshold,
        excluded_keywords=params.excluded_keywords,
    )
    _log_drop("Relevance filter", before, len(listings))

    before = len(listings)
    listings = deduplicate(listings)
    _log_drop("Deduplication", before, len(listings))

    before = len(listings)
    listings = filter_by_salary(listings, params.salary_minimum, params.salary_maximum)
    _log_drop("Salary filter", before, len(listings))

    before = len(listings)
    listings = filter_by_posted_within(listings, params.posted_within_days)
    _log_drop(f"Posted-within filter ({params.posted_within_days}d)", before, len(listings))

    before = len(listings)
    listings = filter_by_seniority(listings, params.seniority_level)
    _log_drop(f"Seniority filter ({params.seniority_level.value})", before, len(listings))

    matched = len(listings)

    if interleave:
        listings = interleave_by_site(listings)

    listings = listings[:max_jobs]
    if matched > len(listings):
        logger.info(
            "Showing %d of %d matching listings. Increase MAX_JOBS_PER_SEARCH for more.",
            len(listings),
            matched,
        )

    return PipelineResult(listings=listings, fetched=fetched, matched=matched)
