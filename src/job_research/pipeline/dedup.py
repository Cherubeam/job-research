"""Cross-source deduplication.

One implementation for every backend. Previously each scraper had its own and
they disagreed: `ClaudeScraper` keyed on the URL alone (so one job cross-posted
under two URLs survived twice), while `JobSpyScraper` keyed on title+company
(so two genuinely different jobs at the same company collapsed into one).

The rule here is: a listing is a duplicate if it shares a normalized URL with
something already kept, **or** if its (title, company, location) identifies the
same posting. Both checks matter — the first catches the same URL reached by
different routes, the second catches the same job listed on Indeed and LinkedIn
under different URLs.
"""

import re
from urllib.parse import urlparse, urlunparse

from job_research.analyzer import JobListing

# Gender markers German postings append to titles. They carry no meaning for
# identity, and boards spell them inconsistently, so they are stripped before
# comparison: "AI Engineer (m/w/d)" and "AI Engineer (all genders)" are one job.
_GENDER_MARKERS = re.compile(
    r"\(?\s*(m\s*[/|]\s*w\s*[/|]\s*d|w\s*[/|]\s*m\s*[/|]\s*d|m\s*[/|]\s*f\s*[/|]\s*d|"
    r"m\s*[/|]\s*w\s*[/|]\s*x|gn|d\s*[/|]\s*m\s*[/|]\s*w|all\s+genders|divers)\s*\)?",
    re.IGNORECASE,
)

# Country and region suffixes boards append inconsistently: one source says
# "Berlin", another "Berlin, Germany", a third "Berlin, Berlin, Deutschland".
# Without trimming these, the same posting looks like two jobs.
_LOCATION_NOISE = frozenset(
    {
        "germany",
        "deutschland",
        "de",
        "remote",
        "hybrid",
        "onsite",
    }
)


def _normalize_url(url: str) -> str:
    """Strip the fragment and any trailing slash so equivalent URLs compare equal."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ""))


def _normalize_text(value: str) -> str:
    value = _GENDER_MARKERS.sub(" ", value.lower())
    return re.sub(r"[^\w]+", " ", value).strip()


def normalize_location(location: str) -> str:
    """Reduce a location to its most specific place name.

    Boards disagree about how much administrative context to append, so only
    the leading component is kept and country/work-mode noise is dropped.
    "Berlin", "Berlin, Germany", and "Berlin, Berlin, Deutschland" all become
    "berlin", while "Berlin" and "Munich" stay distinct.
    """
    head = location.split(",")[0]
    normalized = _normalize_text(head)
    words = [w for w in normalized.split() if w not in _LOCATION_NOISE]
    return " ".join(words)


def identity(listing: JobListing) -> tuple[str, str, str]:
    """The (title, company, location) triple that identifies one posting."""
    return (
        _normalize_text(listing.title),
        _normalize_text(listing.company),
        normalize_location(listing.location),
    )


def deduplicate(listings: list[JobListing]) -> list[JobListing]:
    """Drop later listings that repeat an earlier one. First occurrence wins."""
    seen_urls: set[str] = set()
    seen_identities: set[tuple[str, str, str]] = set()
    result: list[JobListing] = []

    for listing in listings:
        url = listing.job_url.strip()
        normalized_url = _normalize_url(url) if url else ""
        if normalized_url and normalized_url in seen_urls:
            continue

        key = identity(listing)
        if key in seen_identities:
            continue

        if normalized_url:
            seen_urls.add(normalized_url)
        seen_identities.add(key)
        result.append(listing)

    return result
