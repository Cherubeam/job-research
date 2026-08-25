"""Post-fetch filters that narrow a fetched result set to what was asked for.

These run locally, so adjusting them re-filters cached listings instead of
re-running the search.
"""

import logging
import re
from datetime import date, timedelta

from job_research.analyzer import JobListing
from job_research.config import SeniorityLevel

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


def parse_posted_date(raw: str | None) -> date | None:
    """Parse a listing's `posted_date`, or None if it is absent or unrecognised.

    Sources agree on ISO dates often enough to be worth trying and never worth
    relying on: the field is a free string, and the Claude backend passes
    through whatever the page said.
    """
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def filter_by_posted_within(
    listings: list[JobListing], days: int | None, *, today: date | None = None
) -> list[JobListing]:
    """Keep listings published within *days*. `None` disables the filter.

    **Listings with no parseable date are kept**, the same call made for unknown
    salaries: a source that omits the field should not have all its results
    silently dropped. The Bundesagentur backend also applies this server-side
    via `veroeffentlichtseit`, so there it narrows the fetch rather than the
    result set.
    """
    if days is None:
        return listings
    cutoff = (today or date.today()) - timedelta(days=days)
    kept = []
    for listing in listings:
        posted = parse_posted_date(listing.posted_date)
        if posted is None or posted >= cutoff:
            kept.append(listing)
    return kept
