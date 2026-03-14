"""Claude API web search scraper for job listings"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

import anthropic
from pydantic import ValidationError

from job_research.analyzer import JobListing
from job_research.config import JobBoardConfig, JobSearchParams
from job_research.utils import create_cache_key, load_cache, save_cache

logger = logging.getLogger(__name__)

_JOB_BOARD_MAP: dict[str, str] = {
    "search_stepstone": "stepstone.de",
    "search_indeed": "indeed.de",
    "search_linkedin": "linkedin.com",
    "search_monster": "monster.de",
    "search_honeypot": "honeypot.io",
    "search_startups": "startup.jobs",
    "search_arbeitsagentur": "arbeitsagentur.de",
}


def get_active_boards(board_config: JobBoardConfig) -> list[str]:
    """Return domain list for boards that are enabled in *board_config*."""
    return [
        domain
        for field_name, domain in _JOB_BOARD_MAP.items()
        if getattr(board_config, field_name, False)
    ]


class ClaudeScraper:
    """Searches for job listings using the Claude API with the web_search_20250305 tool."""

    def __init__(
        self,
        api_key: str,
        model: str,
        max_jobs: int = 20,
        board_config: Optional[JobBoardConfig] = None,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_jobs = max_jobs
        self._last_call_time: float = 0.0
        self._boards = get_active_boards(board_config or JobBoardConfig())

    # ------------------------------------------------------------------ public

    def search_jobs(
        self,
        params: JobSearchParams,
        cache_dir: Path,
        cache_duration_hours: int = 24,
    ) -> list[JobListing]:
        """Search for jobs matching *params*, using a local cache to avoid repeat API calls."""
        cache_key = create_cache_key(
            "claude_web_search",
            params.keywords,
            params.location,
            work_type=params.work_type.value,
            seniority_level=params.seniority_level.value,
            salary_min=params.salary_minimum,
            salary_max=params.salary_maximum,
        )
        cached = load_cache(cache_dir, cache_key)
        if cached is not None:
            logger.info("Cache hit for key %s", cache_key)
            return [JobListing(**item) for item in cached]

        query = self._build_search_query(params)
        listings, total_items = self._search_and_extract(query)
        logger.info("Extracted %d listings from %d items", len(listings), total_items)

        before_dedup = len(listings)
        listings = self._deduplicate_listings(listings)
        if before_dedup != len(listings):
            logger.info("Dedup removed %d duplicates", before_dedup - len(listings))

        if not listings:
            if total_items == 0:
                raise RuntimeError(
                    "The search completed but no job listings could be extracted. "
                    "The job boards may not have returned relevant results for this query."
                )
            raise RuntimeError(
                f"Found {total_items} items from the search but none had the required fields "
                "(e.g. job title). The search results may not contain structured job listings."
            )

        save_cache(cache_dir, cache_key, [lst.model_dump() for lst in listings], cache_duration_hours)
        logger.info("Found %d listings (saved to cache)", len(listings))
        return listings

    # ----------------------------------------------------------------- private

    def _build_search_query(self, params: JobSearchParams) -> str:
        query_parts = [params.keywords, f"in {params.location}"]
        if params.work_type.value not in ("Any",):
            query_parts.append(params.work_type.value)
        return " ".join(query_parts)

    def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_call_time
        if elapsed < 2.0:
            time.sleep(2.0 - elapsed)
        self._last_call_time = time.time()

    def _make_api_call(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        max_tokens: int = 4096,
        system: Optional[str] = None,
    ) -> anthropic.types.Message:
        self._rate_limit()
        for attempt in range(3):
            try:
                kwargs: dict = {
                    "model": self._model,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                if tools:
                    kwargs["tools"] = tools
                if system:
                    kwargs["system"] = system
                return self._client.messages.create(**kwargs)
            except anthropic.APIStatusError as exc:
                if attempt == 2:
                    raise
                wait = 2**attempt
                logger.warning("API error (attempt %d): %s — retrying in %ds", attempt + 1, exc, wait)
                time.sleep(wait)
        raise RuntimeError("unreachable")

    def _extract_json(self, text: str) -> list | None:
        """Try to parse a JSON array from text, return None on failure."""
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        match = re.search(r"\[.*]", text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group())
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                pass
        return None

    def _search_and_extract(self, query: str) -> tuple[list[JobListing], int]:
        """Single API call: web search + JSON extraction in one prompt."""
        tools = [{
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": 10,
            "allowed_domains": self._boards,
            "user_location": {
                "type": "approximate",
                "country": "DE",
            },
        }]
        system = (
            "You are a job search assistant. Search German job boards using the "
            "web_search tool, then return the results as a JSON array. "
            "No markdown fences, no commentary — output only the JSON array. "
            "Each element must have these fields: "
            "title (string), company (string), location (string), "
            "salary_min (integer or null), salary_max (integer or null), "
            "work_type (string), job_board (string), job_url (string)."
        )
        user_message = f"Find approximately {self._max_jobs} job listings for {query}"
        messages = [{"role": "user", "content": user_message}]
        response = self._make_api_call(messages, tools=tools, system=system)

        raw_text = "\n\n".join(
            block.text for block in response.content if block.type == "text"
        )
        if not raw_text.strip():
            raise RuntimeError(
                "Claude API returned no text content. "
                "The web search may have failed or returned only tool-use blocks."
            )
        logger.info("API response: %d chars of text", len(raw_text))
        logger.debug("Raw API response text: %.500s", raw_text)

        # Strip markdown fences if present
        text = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()

        data = self._extract_json(text)
        if data is None:
            # Model returned narrative instead of JSON — send follow-up turn
            logger.warning("Response was not JSON, sending follow-up extraction request")
            follow_up_messages = [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": raw_text},
                {"role": "user", "content": (
                    "Now output ONLY the JSON array of job listings you found. "
                    "No commentary, no markdown fences — just the raw JSON array."
                )},
            ]
            retry_response = self._make_api_call(follow_up_messages, max_tokens=4096, system=system)
            retry_text = "\n\n".join(
                block.text for block in retry_response.content if block.type == "text"
            )
            retry_text = re.sub(r"```(?:json)?\s*", "", retry_text).strip().rstrip("`").strip()
            data = self._extract_json(retry_text)
            if data is None:
                raise RuntimeError(
                    f"Failed to parse job listings after retry: {retry_text[:200]}"
                )

        listings: list[JobListing] = []
        skipped = 0
        for item in data:
            try:
                listings.append(JobListing(**item))
            except ValidationError:
                skipped += 1
                logger.info("Skipped invalid item: %.100s", item)
        if skipped:
            logger.info("Skipped %d/%d items (validation failed)", skipped, len(data))

        return listings, len(data)

    def _deduplicate_listings(self, listings: list[JobListing]) -> list[JobListing]:
        seen_urls: set[str] = set()
        seen_keys: set[str] = set()
        result = []
        for listing in listings:
            if listing.job_url and listing.job_url.strip():
                if listing.job_url in seen_urls:
                    continue
                seen_urls.add(listing.job_url)
            else:
                key = f"{listing.title.lower()}|{listing.company.lower()}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            result.append(listing)
        return result
