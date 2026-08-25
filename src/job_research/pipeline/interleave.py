"""Round-robin merging of listings across job boards."""

from collections import defaultdict

from job_research.analyzer import JobListing


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
