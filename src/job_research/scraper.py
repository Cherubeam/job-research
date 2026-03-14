"""Claude API web search scraper for job listings"""

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

import anthropic
from pydantic import ValidationError

from job_research.analyzer import JobListing
from job_research.boards import get_adapter
from job_research.config import JobBoardConfig, JobSearchParams
from job_research.utils import create_cache_key, load_cache, save_cache

logger = logging.getLogger(__name__)

_JOB_BOARD_MAP: dict[str, str] = {
    "search_stepstone": "stepstone.de",
    "search_indeed": "de.indeed.com",
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
        self._client = anthropic.Anthropic(api_key=api_key, max_retries=0)
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

    def _get_retry_after(self, exc: anthropic.RateLimitError) -> int:
        """Parse retry-after header from a 429 response, defaulting to 60s."""
        retry_after = exc.response.headers.get("retry-after")
        if retry_after:
            try:
                return max(int(float(retry_after)), 1)
            except (ValueError, TypeError):
                pass
        return 60

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
            except anthropic.RateLimitError as exc:
                if attempt == 2:
                    raise
                retry_after = self._get_retry_after(exc)
                logger.warning(
                    "Rate limited (attempt %d) — retrying in %ds",
                    attempt + 1, retry_after,
                )
                time.sleep(retry_after)
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

    @staticmethod
    def _normalize_url(url: str) -> str:
        """Normalize a URL for comparison: strip fragment, trailing slash."""
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        return urlunparse((parsed.scheme, parsed.netloc, path, parsed.params, parsed.query, ""))

    @staticmethod
    def _extract_search_result_urls(response: anthropic.types.Message) -> set[str]:
        """Extract ground-truth URLs from web_search_tool_result blocks."""
        urls: set[str] = set()
        for block in response.content:
            if getattr(block, "type", None) != "web_search_tool_result":
                continue
            for result in getattr(block, "content", []):
                if getattr(result, "type", None) == "web_search_result":
                    url = getattr(result, "url", None)
                    if url:
                        urls.add(url)
        return urls

    @staticmethod
    def _validate_listing_urls(
        listings: list[JobListing],
        search_urls: set[str],
        boards: list[str],
    ) -> list[JobListing]:
        """Keep only listings whose URL is in search results AND matches a job URL pattern."""
        if not search_urls:
            logger.warning("No search result URLs — skipping validation")
            return listings

        normalized_search = {ClaudeScraper._normalize_url(u) for u in search_urls}
        adapters = [get_adapter(d) for d in boards]

        kept = []
        for listing in listings:
            if not listing.job_url:
                continue
            norm_url = ClaudeScraper._normalize_url(listing.job_url)
            in_search = norm_url in normalized_search
            matches_pattern = any(a.is_job_listing_url(listing.job_url) for a in adapters)

            if in_search and matches_pattern:
                kept.append(listing)
            elif in_search:
                logger.info("Skipped search-page URL: %s", listing.job_url)
            else:
                logger.info("Skipped fabricated URL: %s", listing.job_url)

        discarded = len(listings) - len(kept)
        logger.info("Validated %d/%d listings (%d discarded)", len(kept), len(listings), discarded)
        return kept

    def _build_system_prompt(self) -> str:
        """Build the system prompt with platform-specific search guidance."""
        platform_hints = "\n".join(
            f"- {get_adapter(d).search_hint}" for d in self._boards
        )
        return (
            "You are a job search assistant. Search German job boards using the "
            "web_search tool. You have up to 10 searches — use them strategically:\n\n"
            "1. Start with a broad search to find relevant pages.\n"
            "2. If results are search/category pages, do follow-up searches to find "
            "individual job listing pages. For each promising job, search for:\n"
            "   \"[company name] [job title] site:[job board domain]\"\n"
            "3. Extract job listings ONLY from actual search results — never invent.\n\n"
            f"Extract ALL job listings you find (up to {self._max_jobs}). Include every\n"
            "job whose URL points to an individual listing page — do not cherry-pick\n"
            "or filter based on relevance.\n\n"
            f"Platform-specific guidance:\n{platform_hints}\n\n"
            "Return a JSON array (no markdown fences, no commentary). Each element:\n"
            "  title (string), company (string), location (string),\n"
            "  salary_min (integer or null), salary_max (integer or null),\n"
            "  work_type (string), job_board (string), job_url (string).\n\n"
            "Rules:\n"
            "- job_url MUST be copied verbatim from a web_search result — never construct or guess a URL.\n"
            "- Only include job listings whose URL points to an individual job page, not a search/category page.\n"
            "- Set salary fields to null unless the search result explicitly states a salary.\n"
            "- Skip job listings whose page indicates the position is expired, removed, or no longer available (e.g. \"abgelaufen\", \"nicht mehr verfügbar\").\n"
            "- If you found fewer listings, return fewer. Do not pad results.\n"
            "- Never invent job listings. Only extract jobs explicitly mentioned in search results."
        )

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
        system = self._build_system_prompt()
        user_message = f"Search for {query} job listings and extract what you find"
        messages = [{"role": "user", "content": user_message}]
        response = self._make_api_call(messages, tools=tools, system=system)

        search_urls = self._extract_search_result_urls(response)
        logger.info("Found %d ground-truth URLs from web_search results", len(search_urls))

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

        listings = self._validate_listing_urls(listings, search_urls, self._boards)

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
