"""Running every enabled source in one search, and reporting what happened.

Before this, `SCRAPER_BACKEND` chose one backend and everything else was
unreachable in that run — with Indeed and the Bundesagentur both on by default,
you got one of them. Here each enabled source is assigned to a backend that can
actually reach it, the backends run concurrently, and their results merge into a
single pipeline.

**Per-source outcomes are reported, not swallowed.** A source that fails returns
nothing, which is indistinguishable from a source that genuinely had no matches
unless someone says so. Every source comes back with a status, and one failing
source never takes the whole search down with it.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Protocol

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams
from job_research.sources import Backend, Source, catalog

logger = logging.getLogger(__name__)

# Tried in order when the preferred backend cannot serve a source. Free and
# structured first, metered last: Claude costs money per search, so it is the
# fallback rather than the default route to any source.
_FALLBACK_ORDER = (Backend.BUNDESAGENTUR, Backend.JOBSPY, Backend.CLAUDE)


class JobScraper(Protocol):
    """What the orchestrator needs from a backend."""

    def search_jobs(
        self,
        params: JobSearchParams,
        cache_dir: Path,
        cache_duration_hours: int = 24,
    ) -> list[JobListing]: ...


@dataclass(frozen=True)
class SourceOutcome:
    """What one source contributed to a search, or why it contributed nothing."""

    source: Source
    backend: Backend | None = None
    count: int = 0
    error: str | None = None
    skipped: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None and self.skipped is None

    def describe(self) -> str:
        if self.skipped:
            return f"{self.source.label}: skipped — {self.skipped}"
        if self.error:
            return f"{self.source.label}: failed — {self.error}"
        return (
            f"{self.source.label}: {self.count} via {self.backend.value if self.backend else '?'}"
        )


@dataclass(frozen=True)
class SearchOutcome:
    """Everything one multi-source search produced."""

    listings: list[JobListing] = field(default_factory=list)
    outcomes: list[SourceOutcome] = field(default_factory=list)

    @property
    def failed(self) -> list[SourceOutcome]:
        return [o for o in self.outcomes if o.error]

    @property
    def succeeded(self) -> list[SourceOutcome]:
        return [o for o in self.outcomes if o.ok]

    def summary(self) -> str:
        """One line per source, for the log and the UI."""
        return "\n".join(outcome.describe() for outcome in self.outcomes)


def assign_backends(
    sources: tuple[Source, ...],
    available: set[Backend],
    preferred: Backend | None = None,
) -> tuple[dict[Backend, list[Source]], list[SourceOutcome]]:
    """Group *sources* by the backend that will fetch them.

    The preferred backend wins wherever it can serve the source, so
    `SCRAPER_BACKEND` still means something. Otherwise the first available
    backend in `_FALLBACK_ORDER` takes it. A source no available backend can
    reach is returned as a skipped outcome rather than silently dropped.
    """
    assignments: dict[Backend, list[Source]] = {}
    skipped: list[SourceOutcome] = []

    for source in sources:
        candidates = [preferred] if preferred and source.supports(preferred) else []
        candidates += [b for b in _FALLBACK_ORDER if source.supports(b)]

        backend = next((b for b in candidates if b and b in available), None)
        if backend is None:
            reachable = ", ".join(sorted(b.value for b in source.backends))
            skipped.append(
                SourceOutcome(
                    source=source,
                    skipped=f"needs one of [{reachable}], none configured",
                )
            )
            continue
        assignments.setdefault(backend, []).append(source)

    return assignments, skipped


class Orchestrator:
    """Fans a search out across the backends serving the enabled sources."""

    def __init__(
        self,
        scrapers: dict[Backend, JobScraper],
        *,
        preferred: Backend | None = None,
        max_workers: int = 4,
    ) -> None:
        self._scrapers = scrapers
        self._preferred = preferred
        self._max_workers = max_workers

    def search(
        self,
        params: JobSearchParams,
        cache_dir: Path,
        cache_duration_hours: int = 24,
    ) -> SearchOutcome:
        """Search every enabled source, merging results and per-source status."""
        wanted = tuple(catalog.get(source_id) for source_id in params.enabled_sources)
        assignments, outcomes = assign_backends(wanted, set(self._scrapers), self._preferred)

        if not assignments:
            return SearchOutcome(outcomes=outcomes)

        def run(item: tuple[Backend, list[Source]]) -> tuple[Backend, list[Source], object]:
            backend, sources = item
            scoped = replace(params, enabled_sources=[s.id for s in sources])
            try:
                listings = self._scrapers[backend].search_jobs(
                    params=scoped,
                    cache_dir=cache_dir,
                    cache_duration_hours=cache_duration_hours,
                )
                return backend, sources, listings
            except Exception as exc:  # one bad source must not sink the search
                logger.warning("Backend %s failed: %s", backend.value, exc)
                return backend, sources, exc

        listings: list[JobListing] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            for backend, sources, result in pool.map(run, assignments.items()):
                if isinstance(result, Exception):
                    outcomes.extend(
                        SourceOutcome(source=s, backend=backend, error=str(result)) for s in sources
                    )
                    continue
                found = list(result)  # type: ignore[call-overload]
                listings.extend(found)
                outcomes.extend(
                    _attribute(sources, backend, found)
                    if len(sources) > 1
                    else [SourceOutcome(source=sources[0], backend=backend, count=len(found))]
                )

        outcomes.sort(key=lambda o: o.source.label)
        logger.info("Search outcomes:\n%s", "\n".join(o.describe() for o in outcomes))
        return SearchOutcome(listings=listings, outcomes=outcomes)


def _attribute(
    sources: list[Source], backend: Backend, listings: list[JobListing]
) -> list[SourceOutcome]:
    """Split one backend's results across the sources it fetched for.

    A backend serving several boards (jobspy with Indeed and LinkedIn) returns
    one list, so counts are attributed by each listing's `job_board`. Anything
    unattributable is left out of the counts rather than assigned arbitrarily.
    """
    counts: dict[str, int] = {}
    for listing in listings:
        counts[listing.job_board.lower()] = counts.get(listing.job_board.lower(), 0) + 1
    return [
        SourceOutcome(
            source=source,
            backend=backend,
            count=counts.get(source.id.lower(), counts.get(source.label.lower(), 0)),
        )
        for source in sources
    ]
