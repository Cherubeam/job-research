"""Cross-source deduplication.

Normalization lives in `job_research.identity`, shared with the job store so a
posting's dedup identity and its stored id can never drift apart.

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

from urllib.parse import urlparse, urlunparse

from job_research.analyzer import JobListing
from job_research.identity import identity_key, normalize_location  # noqa: F401  (re-exported)


def _normalize_url(url: str) -> str:
    """Strip the fragment and any trailing slash so equivalent URLs compare equal."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ""))


def identity(listing: JobListing) -> tuple[str, str, str]:
    """The (title, company, location) triple that identifies one posting."""
    return identity_key(listing.title, listing.company, listing.location)


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
