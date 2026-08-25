"""The registry of job sources this tool can search.

Single source of truth for *what exists*: which boards there are, which backends
can reach each one, how to recognise one of its job URLs, and whether it is safe
to enable by default. Previously this knowledge was scattered — seven booleans
in `JobBoardConfig`, a domain map in `scraper.py`, URL patterns in `boards.py`,
and a hardcoded site list inside the jobspy backend that ignored all of them.

Adding a source is one entry here plus, if it needs its own client, a module
under `sources/`.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class Backend(str, Enum):
    """A way of reaching job listings."""

    CLAUDE = "claude"
    """Anthropic web search, restricted to a source's domain."""
    JOBSPY = "jobspy"
    """python-jobspy, which scrapes a fixed set of boards directly."""
    BUNDESAGENTUR = "bundesagentur"
    """The federal job board's own search endpoint. See ADR-001."""


@dataclass(frozen=True)
class Source:
    """One job board, and everything the tool needs to know to search it."""

    id: str
    label: str
    domain: str
    backends: frozenset[Backend]
    job_url_pattern: re.Pattern[str]
    """Matches an *individual listing* URL, so search and category pages are rejected."""
    search_hint: str = ""
    """Guidance handed to the Claude backend's system prompt."""
    jobspy_site: str | None = None
    """This source's name in python-jobspy's `site_name`, when it supports it."""
    default_enabled: bool = False
    caveat: str = ""
    """Shown next to the source in the UI. Non-empty means "read before enabling"."""

    def is_job_listing_url(self, url: str) -> bool:
        return bool(self.job_url_pattern.search(url))

    def supports(self, backend: Backend) -> bool:
        return backend in self.backends


_BOTH = frozenset({Backend.CLAUDE, Backend.JOBSPY})
_CLAUDE_ONLY = frozenset({Backend.CLAUDE})


_SOURCES: tuple[Source, ...] = (
    Source(
        id="indeed",
        label="Indeed.de",
        domain="de.indeed.com",
        backends=_BOTH,
        jobspy_site="indeed",
        default_enabled=True,
        job_url_pattern=re.compile(r"indeed\.\w+/(viewjob|rc/clk)"),
        search_hint=(
            "For Indeed: initial searches often return search/category pages. "
            "To find individual job listings, search for the company name + exact "
            'job title + "indeed" (e.g. "Siemens AI Engineer indeed"). '
            "Valid job URLs contain /viewjob or /rc/clk in the path."
        ),
    ),
    Source(
        id="linkedin",
        label="LinkedIn",
        domain="linkedin.com",
        backends=_BOTH,
        jobspy_site="linkedin",
        job_url_pattern=re.compile(r"linkedin\.com/jobs/view/\d"),
        search_hint="For LinkedIn: individual job URLs contain /jobs/view/<id>.",
        caveat=(
            "Scraping breaches LinkedIn's User Agreement and is heavily rate-limited; "
            "a block returns partial results that look like a thin search. Off by "
            "default — see docs/decisions/002-linkedin-scraping.md."
        ),
    ),
    Source(
        id="stepstone",
        label="StepStone.de",
        domain="stepstone.de",
        backends=_CLAUDE_ONLY,
        job_url_pattern=re.compile(r"stepstone\.de/(stellenangebote--|jobs/\d)"),
        search_hint=(
            "For StepStone: individual job URLs contain /stellenangebote-- or /jobs/<id>."
        ),
    ),
    Source(
        id="monster",
        label="Monster.de",
        domain="monster.de",
        backends=_CLAUDE_ONLY,
        job_url_pattern=re.compile(r"monster\.de/.*job"),
        search_hint="For Monster: look for URLs containing 'job' in the path.",
    ),
    Source(
        id="honeypot",
        label="Honeypot.io",
        domain="honeypot.io",
        backends=_CLAUDE_ONLY,
        job_url_pattern=re.compile(r"honeypot\.io/"),
        search_hint="For Honeypot: any honeypot.io URL with a path is acceptable.",
    ),
    Source(
        id="startups",
        label="startup.jobs",
        domain="startup.jobs",
        backends=_CLAUDE_ONLY,
        job_url_pattern=re.compile(r"startup\.jobs/"),
        search_hint="For startup.jobs: any startup.jobs URL with a path is acceptable.",
    ),
    Source(
        id="arbeitsagentur",
        label="Arbeitsagentur.de",
        domain="arbeitsagentur.de",
        backends=frozenset({Backend.CLAUDE, Backend.BUNDESAGENTUR}),
        job_url_pattern=re.compile(r"arbeitsagentur\.de/"),
        search_hint="For Arbeitsagentur: any arbeitsagentur.de URL with a path is acceptable.",
        caveat=(
            "Federal job board. Off by default — see docs/decisions/"
            "001-bundesagentur-terms-of-use.md before enabling."
        ),
    ),
)

_BY_ID: dict[str, Source] = {source.id: source for source in _SOURCES}

KNOWN_IDS: frozenset[str] = frozenset(_BY_ID)
DEFAULT_ENABLED: frozenset[str] = frozenset(s.id for s in _SOURCES if s.default_enabled)


class UnknownSourceError(KeyError):
    """Raised for a source id that is not in the registry."""


def all_sources() -> tuple[Source, ...]:
    """Every registered source, in display order."""
    return _SOURCES


def get(source_id: str) -> Source:
    try:
        return _BY_ID[source_id]
    except KeyError:
        known = ", ".join(sorted(KNOWN_IDS))
        raise UnknownSourceError(f"Unknown source {source_id!r}. Known sources: {known}") from None


def for_backend(backend: Backend) -> tuple[Source, ...]:
    """Every source *backend* is able to reach."""
    return tuple(source for source in _SOURCES if source.supports(backend))


def resolve(source_ids: Iterable[str], backend: Backend) -> tuple[Source, ...]:
    """Resolve *source_ids* to the subset *backend* can actually reach.

    Ids the backend cannot serve are dropped rather than raising: enabling
    StepStone and then switching to the jobspy backend should quietly search
    less, not fail. Unknown ids still raise, since those are configuration
    errors rather than a backend mismatch.
    """
    wanted = [get(source_id) for source_id in source_ids]
    return tuple(source for source in wanted if source.supports(backend))
