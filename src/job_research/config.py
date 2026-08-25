"""Configuration management for job research tool"""

import json
import logging
import os
from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from job_research.sources import catalog

logger = logging.getLogger(__name__)


_LEGACY_SOURCE_VARS = {
    "SEARCH_STEPSTONE": "stepstone",
    "SEARCH_INDEED": "indeed",
    "SEARCH_LINKEDIN": "linkedin",
    "SEARCH_MONSTER": "monster",
    "SEARCH_HONEYPOT": "honeypot",
    "SEARCH_STARTUPS": "startups",
    "SEARCH_ARBEITSAGENTUR": "arbeitsagentur",
}


def _enabled_sources_from_env() -> list[str]:
    """Read `ENABLED_SOURCES`, falling back to the legacy `SEARCH_*` booleans.

    The fallback exists so an existing `.env` keeps working rather than silently
    changing which boards get searched. Unknown ids are dropped with a warning:
    a typo should cost you one source, not the whole run.
    """
    raw = _split_list(os.getenv("ENABLED_SOURCES", ""))
    if not raw:
        legacy = [
            source_id
            for var, source_id in _LEGACY_SOURCE_VARS.items()
            if os.getenv(var, "").lower() == "true"
        ]
        if legacy:
            logger.warning(
                "SEARCH_* variables are deprecated; use ENABLED_SOURCES=%s",
                ",".join(sorted(legacy)),
            )
            return sorted(legacy)
        return sorted(catalog.DEFAULT_ENABLED)

    known = [source_id for source_id in raw if source_id in catalog.KNOWN_IDS]
    for source_id in set(raw) - catalog.KNOWN_IDS:
        logger.warning(
            "Ignoring unknown source %r in ENABLED_SOURCES. Known: %s",
            source_id,
            ", ".join(sorted(catalog.KNOWN_IDS)),
        )
    return known or sorted(catalog.DEFAULT_ENABLED)


def _split_list(raw: str) -> list[str]:
    """Parse a comma-separated env var into a list, dropping blanks."""
    return [item.strip() for item in raw.split(",") if item.strip()]


class SeniorityLevel(str, Enum):
    """Job seniority levels"""

    JUNIOR = "Junior"
    MID_LEVEL = "Mid-level"
    SENIOR = "Senior"
    ALL = "All levels"


class WorkType(str, Enum):
    """Work arrangement types"""

    REMOTE = "Remote only"
    HYBRID = "Remote/Hybrid"
    ONSITE = "Onsite only"
    ANY = "Any"


class OutputFormat(str, Enum):
    """Output file formats"""

    MARKDOWN = "markdown"
    CSV = "csv"
    JSON = "json"


class ScraperBackend(str, Enum):
    """Available scraper backends"""

    CLAUDE = "claude"
    JOBSPY = "jobspy"


@dataclass
class JobSearchParams:
    """Parameters for job search"""

    keywords: str = "AI Engineer"
    job_title_alternatives: list[str] = field(
        default_factory=lambda: [
            "Machine Learning Engineer",
            "ML Engineer",
            "Artificial Intelligence Engineer",
            "Deep Learning Engineer",
        ]
    )
    location: str = "All of Germany"
    specific_cities: list[str] = field(default_factory=list)
    country_code: str = "DE"
    work_type: WorkType = WorkType.HYBRID
    seniority_level: SeniorityLevel = SeniorityLevel.ALL
    years_experience_min: int = 0
    years_experience_max: int = 50
    salary_minimum: int = 50000
    salary_maximum: int = 200000
    currency: str = "EUR"
    industries: list[str] = field(default_factory=lambda: ["All"])
    enabled_sources: list[str] = field(default_factory=lambda: sorted(catalog.DEFAULT_ENABLED))
    """Source ids to search. Ids the active backend cannot reach are skipped."""
    excluded_keywords: list[str] = field(default_factory=list)
    """Titles containing any of these phrases are dropped outright."""
    relevance_threshold: float = 0.6
    """Fraction of a search phrase a title must cover to be kept. See pipeline.relevance."""


@dataclass
class OutputConfig:
    """Output configuration"""

    output_directory: Path = field(default_factory=lambda: Path.cwd() / "data" / "results")
    output_format: OutputFormat = OutputFormat.MARKDOWN
    generate_summary: bool = True
    generate_salary_analysis: bool = True
    cache_directory: Path = field(default_factory=lambda: Path.cwd() / "data" / "cache")
    cache_results: bool = True
    cache_duration_hours: int = 24
    send_email_notification: bool = False
    email_recipient: Optional[str] = None


def mask_secret(value: Optional[str]) -> str:
    """Render a credential for display without revealing it.

    Returned already quoted, so it drops straight into a repr. Anything short
    enough that a prefix and suffix would give most of it away is hidden
    entirely.
    """
    if not value:
        return repr(value)
    if len(value) <= 16:
        return "'***'"
    return f"'{value[:7]}…{value[-6:]}'"


@dataclass
class Config:
    """Main configuration class"""

    search_params: JobSearchParams = field(default_factory=JobSearchParams)
    output: OutputConfig = field(default_factory=OutputConfig)
    verbose: bool = False
    scraper_backend: ScraperBackend = ScraperBackend.CLAUDE
    claude_api_key: Optional[str] = None
    claude_model: str = "claude-haiku-4-5-20251001"
    max_jobs_per_search: int = 200
    interleave_sites: bool = True

    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        load_dotenv()

        search_params = JobSearchParams(
            keywords=os.getenv("JOB_KEYWORDS", "AI Engineer"),
            location=os.getenv("LOCATION", "All of Germany"),
            work_type=WorkType(os.getenv("WORK_TYPE", "Remote/Hybrid")),
            seniority_level=SeniorityLevel(os.getenv("SENIORITY_LEVELS", "All levels")),
            salary_minimum=int(os.getenv("SALARY_MINIMUM", "50000")),
            salary_maximum=int(os.getenv("SALARY_MAXIMUM", "200000")),
            enabled_sources=_enabled_sources_from_env(),
            excluded_keywords=_split_list(os.getenv("EXCLUDED_KEYWORDS", "")),
            relevance_threshold=float(os.getenv("RELEVANCE_THRESHOLD", "0.6")),
        )

        output = OutputConfig(
            output_directory=Path(os.getenv("OUTPUT_DIRECTORY", "data/results")),
            output_format=OutputFormat(os.getenv("OUTPUT_FORMAT", "markdown")),
            cache_duration_hours=int(os.getenv("CACHE_DURATION_HOURS", "24")),
        )

        return cls(
            search_params=search_params,
            output=output,
            verbose=os.getenv("VERBOSE", "false").lower() == "true",
            scraper_backend=ScraperBackend(os.getenv("SCRAPER_BACKEND", "claude")),
            claude_api_key=os.getenv("CLAUDE_API_KEY"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001"),
            max_jobs_per_search=int(os.getenv("MAX_JOBS_PER_SEARCH", "200")),
            interleave_sites=os.getenv("INTERLEAVE_SITES", "true").lower() == "true",
        )

    def __repr__(self) -> str:
        """Mask `claude_api_key`, so no traceback, log line, or bug report leaks it.

        Built from `fields()` rather than written out, so it cannot drift as
        fields are added. Note this protects incidental printing of the *config*;
        `self.claude_api_key` is still the raw value for callers that need it.
        """
        rendered = [
            f"{f.name}="
            + (
                mask_secret(self.claude_api_key)
                if f.name == "claude_api_key"
                else repr(getattr(self, f.name))
            )
            for f in fields(self)
        ]
        return f"{type(self).__name__}({', '.join(rendered)})"

    @classmethod
    def from_json(cls, filepath: Path) -> "Config":
        """Load configuration from JSON file"""
        with open(filepath, "r") as f:
            data = json.load(f)

        search_params = JobSearchParams(**data.get("search_params", {}))
        output = OutputConfig(**data.get("output", {}))

        return cls(
            search_params=search_params,
            output=output,
            verbose=data.get("verbose", False),
        )

    def to_dict(self) -> dict:
        """Serialize to plain JSON-compatible types.

        Generated from `fields()` so it cannot drift as fields are added — the
        hand-written version was already missing `scraper_backend`,
        `claude_model`, `max_jobs_per_search`, and `interleave_sites`. The API
        key is excluded: this is written to disk and pasted into issues.
        """

        def _plain(value: object) -> object:
            if isinstance(value, Enum):
                return value.value
            if isinstance(value, Path):
                return str(value)
            if is_dataclass(value) and not isinstance(value, type):
                return {f.name: _plain(getattr(value, f.name)) for f in fields(value)}
            if isinstance(value, (list, tuple)):
                return [_plain(item) for item in value]
            return value

        return {
            f.name: _plain(getattr(self, f.name))
            for f in fields(self)
            if f.name != "claude_api_key"
        }
