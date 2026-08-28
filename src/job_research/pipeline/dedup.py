"""Cross-source deduplication.

Normalization lives in `job_research.identity`, shared with the job store so a
posting's dedup identity and its stored id can never drift apart.

One implementation for every backend. Previously each scraper had its own and
they disagreed: `LLMScraper` (then `ClaudeScraper`) keyed on the URL alone (so one job cross-posted
under two URLs survived twice), while `JobSpyScraper` keyed on title+company
(so two genuinely different jobs at the same company collapsed into one).

The rule here is: a listing is a duplicate if it shares a normalized URL with
something already kept, **or** if its (title, company, location) identifies the
same posting. Both checks matter — the first catches the same URL reached by
different routes, the second catches the same job listed on Indeed and LinkedIn
under different URLs.
"""

from urllib.parse import urlparse, urlunparse

from job_research.analyzer import JobListing, SourceRef
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
    """Collapse repeats, keeping the first occurrence and its provenance.

    A dropped duplicate is not simply discarded: its board and URL are recorded
    on the survivor's `alternates`. With several sources enabled the same job
    genuinely appears on several boards, and knowing that is useful — it is also
    how you reach the posting again if one board pulls it.
    """
    seen_urls: set[str] = set()
    by_identity: dict[tuple[str, str, str], JobListing] = {}
    order: list[tuple[str, str, str]] = []

    for listing in listings:
        url = listing.job_url.strip()
        normalized_url = _normalize_url(url) if url else ""
        key = identity(listing)

        duplicate_of = by_identity.get(key)
        if duplicate_of is None and normalized_url and normalized_url in seen_urls:
            # Same URL under a different identity: find the listing holding it.
            duplicate_of = next(
                (
                    kept
                    for kept in by_identity.values()
                    if kept.job_url and _normalize_url(kept.job_url) == normalized_url
                ),
                None,
            )

        if duplicate_of is not None:
            _add_alternate(duplicate_of, listing)
            continue

        if normalized_url:
            seen_urls.add(normalized_url)
        by_identity[key] = listing
        order.append(key)

    return [by_identity[key] for key in order]


def _add_alternate(kept: JobListing, duplicate: JobListing) -> None:
    """Record where else *duplicate* was found, without repeating what we have."""
    if not duplicate.job_board and not duplicate.job_url:
        return
    known_urls = {kept.job_url, *(ref.job_url for ref in kept.alternates)}
    if duplicate.job_url and duplicate.job_url in known_urls:
        return
    kept.alternates.append(SourceRef(job_board=duplicate.job_board, job_url=duplicate.job_url))
