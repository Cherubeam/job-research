"""Bundesagentur für Arbeit "Jobsuche" — client and scraper backend.

Germany's federal job board, and by a wide margin the largest German corpus.
Ported from the working client in the sibling `mhp-bd-intelligence` project,
which consumes the employer *facet*; this consumes the posting list instead.

**Read `docs/decisions/001-bundesagentur-terms-of-use.md` before changing
anything here.** The endpoint is reverse-engineered rather than official, and
BA's portal terms restrict automated read-out. The source is opt-in and off by
default, and this module deliberately does not paginate without bound.

Two operational facts carried over from that project's spike:

* **The API version moves without notice.** BA retired `pc/v4` server-side on
  2026-08-04 and every query began returning 404. `base_url` is therefore
  injectable and the response parser accepts both the v6 and v4 shapes.
* **A zero-result query does not return an empty employer facet** — it falls
  back to a global top-employers histogram. This module reads the posting list
  rather than the facet, so it is unaffected, but anything added here that
  touches `facetten` must guard on `maxErgebnisse > 0`.
"""

import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams, WorkType
from job_research.salary import to_annual
from job_research.utils import create_cache_key, load_cache, save_cache

logger = logging.getLogger(__name__)

BASE_URL = "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6"
"""v6 since 2026-08-04, when BA retired pc/v4 server-side."""

API_KEY = "jobboerse-jobsuche"
"""Static client id published in BA's own mobile app. Not a secret, not issued to us."""

DETAIL_URL_TEMPLATE = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"

MAX_PAGE_SIZE = 100
MAX_PAGES = 5
"""Hard ceiling on pages per search. ADR-001 constraint: no bulk enumeration."""

# BA's `arbeitszeit` filter. "ho" is Homeoffice/Telearbeit — the only one of our
# work types the API can express. Onsite has no positive filter (excluding "ho"
# is not offered), so it is left to the local pipeline.
_WORK_TIME_PARAM = {WorkType.REMOTE: "ho"}

# `verguetungsangabe` states the pay *period*; `artDerVerguetung` states whether
# the amount is a range or a fixed figure. Verified live 2026-08-25: roughly a
# third of postings carry structured pay, which is more than any other source
# here exposes.
_PAY_PERIOD = {
    "JAHRESGEHALT": "year",
    "MONATSGEHALT": "month",
    "STUNDENLOHN": "hour",
}


class BundesagenturError(RuntimeError):
    """A Jobsuche request failed or returned something unusable."""


def _first(payload: dict[str, Any], *keys: str) -> Any:
    """Return the first present, non-empty value among *keys*.

    The v6 and v4 shapes disagree about several field names, and BA has changed
    them before without notice. Reading tolerantly costs nothing and means a
    rename degrades one field rather than breaking the whole source.
    """
    for key in keys:
        value = payload.get(key)
        if value not in (None, "", [], {}):
            return value
    return None


def _nested(payload: dict[str, Any], key: str, subkey: str) -> Any:
    """Read `payload[key][subkey]` when both exist."""
    value = payload.get(key)
    return value.get(subkey) if isinstance(value, dict) else None


def _format_location(stellenlokationen: Any) -> str:
    """Take the primary work location from BA's `stellenlokationen` list.

    A posting can carry several locations (the same role advertised in München,
    Bonn, and Berlingen). `JobListing` holds one, and joining them would defeat
    the dedup key, so the first is used — which is the one BA ranks first.
    """
    if not isinstance(stellenlokationen, list) or not stellenlokationen:
        return ""
    first = stellenlokationen[0]
    if not isinstance(first, dict):
        return ""
    adresse = first.get("adresse")
    if not isinstance(adresse, dict):
        return ""
    return str(adresse.get("ort") or "")


def _work_type(posting: dict[str, Any]) -> str:
    """Map BA's boolean working-time flags to a display string."""
    if posting.get("homeofficemoeglich") is True:
        return "Remote"
    if posting.get("arbeitszeitVollzeit") is True:
        return "Full-time"
    if any(
        posting.get(key) is True
        for key in (
            "arbeitszeitTeilzeitFlexibel",
            "arbeitszeitTeilzeitVormittag",
            "arbeitszeitTeilzeitNachmittag",
            "arbeitszeitTeilzeitAbend",
        )
    ):
        return "Part-time"
    return ""


class JobsucheClient:
    """Thin client over the Jobsuche search endpoint.

    Scoped to a bounded, user-initiated search: no facet reads, no unbounded
    pagination, no posting-detail retrieval.
    """

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        api_key: str = API_KEY,
        timeout_seconds: float = 20.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds

    def search(
        self,
        *,
        what: str,
        where: str | None = None,
        published_since_days: int | None = None,
        work_time: str | None = None,
        size: int = MAX_PAGE_SIZE,
        page: int = 1,
    ) -> tuple[list[dict[str, Any]], int]:
        """Return one page of postings and the reported total result count."""
        params: dict[str, str | int] = {
            "was": what,
            "size": min(size, MAX_PAGE_SIZE),
            "page": page,
            # 1 = ARBEIT. Without it the corpus also returns apprenticeships,
            # dual study places, and self-employment offers.
            "angebotsart": 1,
        }
        if where:
            params["wo"] = where
        if published_since_days is not None:
            params["veroeffentlichtseit"] = published_since_days
        if work_time:
            params["arbeitszeit"] = work_time

        try:
            response = requests.get(
                f"{self._base_url}/jobs",
                params=params,
                headers={"X-API-Key": self._api_key},
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BundesagenturError(
                f"Jobsuche request failed for {what!r}: {exc}. "
                "The endpoint is unofficial and has changed without notice before "
                "(see docs/decisions/001-bundesagentur-terms-of-use.md)."
            ) from exc

        try:
            payload: dict[str, Any] = response.json()
        except ValueError as exc:
            raise BundesagenturError(
                f"Jobsuche returned a non-JSON body for {what!r}: {exc}"
            ) from exc

        postings = _first(payload, "ergebnisliste", "stellenangebote") or []
        total = payload.get("maxErgebnisse")
        return list(postings), int(total) if isinstance(total, int) else len(postings)


def _salary(posting: dict[str, Any]) -> tuple[int | None, int | None]:
    """Read BA's structured pay fields and annualise them.

    Unlike every other source here, BA states the period explicitly, so no
    guessing is needed. An unrecognised period yields no salary rather than a
    figure that would silently skew the statistics — an hourly rate recorded as
    annual is worse than a blank.
    """
    period_code = posting.get("verguetungsangabe")
    if not isinstance(period_code, str) or period_code == "KEINE_ANGABEN":
        return None, None
    period = _PAY_PERIOD.get(period_code)
    if period is None:
        logger.info("Unrecognised Bundesagentur pay period %r — ignoring salary", period_code)
        return None, None

    low = posting.get("gehaltsspanneVon")
    high = posting.get("gehaltsspanneBis")
    fixed = posting.get("festgehalt")
    if low is None and high is None and fixed is not None:
        low = high = fixed

    return (
        to_annual(float(low), period) if isinstance(low, (int, float)) else None,
        to_annual(float(high), period) if isinstance(high, (int, float)) else None,
    )


def to_job_listing(posting: dict[str, Any]) -> JobListing | None:
    """Map one Jobsuche posting to a `JobListing`, or None if it has no title.

    Field names verified against a live v6 response on 2026-08-25 with
    `scripts/probe_bundesagentur.py`. They are *not* the names the sibling MHP
    client uses — that one reads only the employer facet and posting titles, so
    it never touched these. Alternative names are accepted where BA has offered
    more than one, since the endpoint is unofficial and has been renamed before.
    """
    title = _first(posting, "stellenangebotsTitel", "titel", "hauptberuf")
    if not title:
        return None

    reference = _first(posting, "referenznummer", "refnr", "hashId")
    job_url = DETAIL_URL_TEMPLATE.format(refnr=quote(str(reference), safe="")) if reference else ""

    posted = _first(posting, "datumErsteVeroeffentlichung") or _nested(
        posting, "veroeffentlichungszeitraum", "von"
    )

    salary_min, salary_max = _salary(posting)

    return JobListing(
        title=str(title),
        company=str(_first(posting, "firma", "arbeitgeber") or ""),
        location=_format_location(_first(posting, "stellenlokationen")),
        salary_min=salary_min,
        salary_max=salary_max,
        job_url=job_url,
        job_board="Arbeitsagentur",
        work_type=_work_type(posting),
        posted_date=str(posted) if posted else None,
    )


class BundesagenturScraper:
    """`JobScraper` backend for the federal job board."""

    def __init__(self, max_jobs: int = 20, client: JobsucheClient | None = None) -> None:
        self._max_jobs = max_jobs
        self._client = client or JobsucheClient()

    @property
    def _results_wanted(self) -> int:
        """Overfetch, since relevance filtering discards part of what comes back."""
        return int(self._max_jobs * 1.5)

    def search_jobs(
        self,
        params: JobSearchParams,
        cache_dir: Path,
        cache_duration_hours: int = 24,
    ) -> list[JobListing]:
        """Fetch listings for *params*, using a local cache."""
        where = None if params.location == "All of Germany" else params.location
        work_time = _WORK_TIME_PARAM.get(params.work_type)

        cache_key = create_cache_key(
            "bundesagentur",
            keywords=params.keywords,
            location=where,
            work_time=work_time,
            posted_within_days=params.posted_within_days,
            results_wanted=self._results_wanted,
        )
        cached = load_cache(cache_dir, cache_key)
        if cached is not None:
            logger.info("Cache hit for key %s (%d listings)", cache_key, len(cached))
            return [JobListing(**item) for item in cached]

        listings = self._fetch(params.keywords, where, work_time, params.posted_within_days)

        if not listings:
            raise BundesagenturError(
                "Bundesagentur returned no listings for this search. "
                "Its corpus is dense for Mittelstand, public sector, and traditional "
                "industry, and sparse for digital-native employers — an empty result "
                "may mean the source is blind here rather than that nobody is hiring."
            )

        save_cache(
            cache_dir, cache_key, [lst.model_dump() for lst in listings], cache_duration_hours
        )
        logger.info("Found %d listings (saved to cache)", len(listings))
        return listings

    def _fetch(
        self,
        keywords: str,
        where: str | None,
        work_time: str | None,
        published_since_days: int | None,
    ) -> list[JobListing]:
        listings: list[JobListing] = []
        skipped = 0

        for page in range(1, MAX_PAGES + 1):
            if len(listings) >= self._results_wanted:
                break

            postings, total = self._client.search(
                what=keywords,
                where=where,
                published_since_days=published_since_days,
                work_time=work_time,
                size=MAX_PAGE_SIZE,
                page=page,
            )
            if page == 1:
                logger.info("Bundesagentur reports %d total results for %r", total, keywords)
            if not postings:
                break

            for posting in postings:
                listing = to_job_listing(posting)
                if listing is None:
                    skipped += 1
                    continue
                listings.append(listing)

            if len(postings) < MAX_PAGE_SIZE:
                break
        else:
            # Loop ran to MAX_PAGES without breaking: say so rather than let the
            # result silently look complete.
            logger.info(
                "Stopped at the %d-page ceiling; more results exist but are not fetched.",
                MAX_PAGES,
            )

        if skipped:
            logger.info("Skipped %d postings with no usable title", skipped)
        logger.info("Fetched %d listings from Bundesagentur", len(listings))
        return listings[: self._results_wanted]
