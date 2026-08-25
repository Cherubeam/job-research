"""Post-fetch processing shared by every scraper backend.

Scrapers fetch and normalize; this module decides what the user actually sees.
Keeping the two apart means a filter written once applies to every backend, and
that the cache can hold the raw fetch while the view varies freely on top of it.

Order matters: filter, then interleave, then truncate. Truncating first would
cut listings that filtering was about to remove anyway, leaving fewer results
than requested for no reason.

Phase 2 of `docs/architecture-review.md` splits this module into a package
(`relevance.py`, `dedup.py`, `filters.py`, `interleave.py`) and moves
deduplication in from the scrapers.
"""

import logging
import re
from collections import defaultdict
from dataclasses import dataclass

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, SeniorityLevel

logger = logging.getLogger(__name__)

# Title markers used to infer seniority. Matched case-insensitively on word
# boundaries against the job title, so "lead" does not fire inside "leadership".
_JUNIOR_MARKERS = frozenset(
    {
        "junior",
        "jr",
        "intern",
        "internship",
        "praktikum",
        "praktikant",
        "praktikantin",
        "werkstudent",
        "werkstudentin",
        "trainee",
        "einsteiger",
        "berufseinsteiger",
        "entry",
        "graduate",
        "absolvent",
        "absolventin",
        "student",
        "studentische",
        "ausbildung",
        "azubi",
    }
)

_SENIOR_MARKERS = frozenset(
    {
        "senior",
        "sr",
        "lead",
        "leiter",
        "leiterin",
        "leitung",
        "principal",
        "staff",
        "head",
        "chief",
        "director",
        "vp",
        "expert",
        "experte",
        "expertin",
        "architect",
        "architekt",
        "architektin",
    }
)


# German builds seniority into compounds — "Teamleiter", "Projektleiter",
# "Abteilungsleitung" — where whole-word matching finds nothing. These are
# matched as suffixes instead, with the false friends that would otherwise be
# caught listed explicitly.
_SENIOR_SUFFIXES = ("leiter", "leiterin", "leitung")
_SENIOR_SUFFIX_FALSE_FRIENDS = ("begleiter", "begleiterin", "begleitung")


def _title_tokens(title: str) -> set[str]:
    return {token for token in re.split(r"[^\w]+", title.lower()) if token}


def _has_senior_compound(tokens: set[str]) -> bool:
    return any(
        token.endswith(suffix)
        and len(token) > len(suffix)
        and not token.endswith(_SENIOR_SUFFIX_FALSE_FRIENDS)
        for token in tokens
        for suffix in _SENIOR_SUFFIXES
    )


def infer_seniority(title: str) -> SeniorityLevel:
    """Infer a seniority level from a job title.

    A best-effort heuristic on title markers only — job boards do not expose a
    reliable structured seniority field. A title carrying neither a junior nor a
    senior marker is reported as mid-level, which is also what an unrecognised
    title falls back to. Junior markers win over senior ones so that
    "Junior Architect" is not read as senior.
    """
    tokens = _title_tokens(title)
    if tokens & _JUNIOR_MARKERS:
        return SeniorityLevel.JUNIOR
    if tokens & _SENIOR_MARKERS or _has_senior_compound(tokens):
        return SeniorityLevel.SENIOR
    return SeniorityLevel.MID_LEVEL


def filter_by_seniority(listings: list[JobListing], level: SeniorityLevel) -> list[JobListing]:
    """Keep listings whose title implies *level*. `ALL` disables the filter."""
    if level == SeniorityLevel.ALL:
        return listings
    return [lst for lst in listings if infer_seniority(lst.title) == level]


def filter_by_salary(listings: list[JobListing], minimum: int, maximum: int) -> list[JobListing]:
    """Keep listings whose stated salary range overlaps [*minimum*, *maximum*].

    **Listings without salary information are kept.** Most German postings omit
    salary entirely, so dropping them would discard the majority of real results
    to enforce a bound the posting never stated. Only a listing that explicitly
    states a range falling wholly outside the requested window is removed.
    """
    kept = []
    for listing in listings:
        # A missing bound means unbounded on that side, not zero: "ab 60.000 €"
        # parses to (60000, None) and must still match a window ending above it.
        # A listing with neither bound is unbounded both ways, so it always
        # overlaps — which is how "unknown salary is kept" falls out.
        low = listing.salary_min if listing.salary_min is not None else float("-inf")
        high = listing.salary_max if listing.salary_max is not None else float("inf")
        if low <= maximum and high >= minimum:
            kept.append(listing)
    return kept


def interleave_by_site(listings: list[JobListing]) -> list[JobListing]:
    """Round-robin listings across job boards, preserving order within each board.

    Without this, truncating to `max_jobs` can return results from a single
    board simply because it was scraped first.
    """
    by_site: dict[str, list[JobListing]] = defaultdict(list)
    for listing in listings:
        by_site[listing.job_board or "unknown"].append(listing)

    result: list[JobListing] = []
    site_iters = [iter(jobs) for jobs in by_site.values()]
    while site_iters:
        exhausted = []
        for i, iterator in enumerate(site_iters):
            value = next(iterator, None)
            if value is not None:
                result.append(value)
            else:
                exhausted.append(i)
        for i in reversed(exhausted):
            site_iters.pop(i)
    return result


@dataclass(frozen=True)
class PipelineResult:
    """Listings to display, plus the counts needed to explain what happened."""

    listings: list[JobListing]
    fetched: int
    """Listings the scraper returned, before any filtering."""
    matched: int
    """Listings that survived filtering, before truncation to `max_jobs`."""

    @property
    def truncated(self) -> bool:
        return self.matched > len(self.listings)


def apply(
    listings: list[JobListing],
    params: JobSearchParams,
    *,
    max_jobs: int,
    interleave: bool = True,
) -> PipelineResult:
    """Filter, interleave, and truncate a scraper's raw output for display."""
    fetched = len(listings)

    before = len(listings)
    listings = filter_by_salary(listings, params.salary_minimum, params.salary_maximum)
    if before != len(listings):
        logger.info("Salary filter removed %d listings", before - len(listings))

    before = len(listings)
    listings = filter_by_seniority(listings, params.seniority_level)
    if before != len(listings):
        logger.info(
            "Seniority filter (%s) removed %d listings",
            params.seniority_level.value,
            before - len(listings),
        )

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
