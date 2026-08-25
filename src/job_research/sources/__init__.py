"""Job sources: the registry of what can be searched, and per-source clients."""

from job_research.sources.catalog import (
    DEFAULT_ENABLED,
    KNOWN_IDS,
    Backend,
    Source,
    UnknownSourceError,
    all_sources,
    for_backend,
    get,
    resolve,
)

__all__ = [
    "DEFAULT_ENABLED",
    "KNOWN_IDS",
    "Backend",
    "Source",
    "UnknownSourceError",
    "all_sources",
    "for_backend",
    "get",
    "resolve",
]
