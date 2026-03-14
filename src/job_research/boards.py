"""Platform adapters for deterministic job listing URL validation."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class JobBoardAdapter:
    """Matches individual job listing URLs for a specific job board."""

    domain: str
    job_url_pattern: re.Pattern[str]
    search_hint: str

    def is_job_listing_url(self, url: str) -> bool:
        return bool(self.job_url_pattern.search(url))


_ADAPTERS: dict[str, JobBoardAdapter] = {
    "indeed.de": JobBoardAdapter(
        domain="indeed.de",
        job_url_pattern=re.compile(r"indeed\.\w+/(viewjob|rc/clk|jobs\?)"),
        search_hint=(
            "For Indeed: search pages list many jobs — follow up with searches "
            "for specific job titles + company names to find individual viewjob URLs."
        ),
    ),
    "stepstone.de": JobBoardAdapter(
        domain="stepstone.de",
        job_url_pattern=re.compile(r"stepstone\.de/(stellenangebote--|jobs/\d)"),
        search_hint=(
            "For StepStone: individual job URLs contain /stellenangebote-- or /jobs/<id>."
        ),
    ),
    "linkedin.com": JobBoardAdapter(
        domain="linkedin.com",
        job_url_pattern=re.compile(r"linkedin\.com/jobs/view/\d"),
        search_hint=(
            "For LinkedIn: individual job URLs contain /jobs/view/<id>."
        ),
    ),
    "monster.de": JobBoardAdapter(
        domain="monster.de",
        job_url_pattern=re.compile(r"monster\.de/.*job"),
        search_hint="For Monster: look for URLs containing 'job' in the path.",
    ),
    "honeypot.io": JobBoardAdapter(
        domain="honeypot.io",
        job_url_pattern=re.compile(r"honeypot\.io/"),
        search_hint="For Honeypot: any honeypot.io URL with a path is acceptable.",
    ),
    "startup.jobs": JobBoardAdapter(
        domain="startup.jobs",
        job_url_pattern=re.compile(r"startup\.jobs/"),
        search_hint="For startup.jobs: any startup.jobs URL with a path is acceptable.",
    ),
    "arbeitsagentur.de": JobBoardAdapter(
        domain="arbeitsagentur.de",
        job_url_pattern=re.compile(r"arbeitsagentur\.de/"),
        search_hint="For Arbeitsagentur: any arbeitsagentur.de URL with a path is acceptable.",
    ),
}


def get_adapter(domain: str) -> JobBoardAdapter:
    """Return the adapter for *domain*, or a fallback that matches any URL on it."""
    if domain in _ADAPTERS:
        return _ADAPTERS[domain]
    escaped = re.escape(domain)
    return JobBoardAdapter(
        domain=domain,
        job_url_pattern=re.compile(rf"{escaped}/"),
        search_hint=f"For {domain}: any URL on this domain is acceptable.",
    )
