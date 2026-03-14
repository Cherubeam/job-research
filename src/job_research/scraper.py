"""Claude API web search scraper for job listings"""

import json
import logging
import re
import time
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import anthropic

from job_research.analyzer import JobListing
from job_research.config import JobBoardConfig, JobSearchParams
from job_research.utils import create_cache_key, load_cache, save_cache

logger = logging.getLogger(__name__)

_JOB_BOARD_MAP: dict[str, str] = {
    "search_stepstone": "stepstone.de",
    "search_indeed": "indeed.de",
    "search_linkedin": "linkedin.com",
    "search_xing": "xing.com",
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
        try:
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
            raw = self._claude_web_search(query)
            listings = self._parse_results(raw, params)
            listings = self._deduplicate_listings(listings)

            save_cache(cache_dir, cache_key, [asdict(l) for l in listings], cache_duration_hours)
            logger.info("Found %d listings (saved to cache)", len(listings))
            return listings

        except Exception:
            logger.exception("search_jobs failed")
            return []

    # ----------------------------------------------------------------- private

    def _build_search_query(self, params: JobSearchParams) -> str:
        query_parts = [params.keywords, f"in {params.location}"]
        if params.work_type.value not in ("Any",):
            query_parts.append(params.work_type.value)

        site_clause = " OR ".join(f"site:{b}" for b in self._boards)
        instruction = (
            f"Find approximately {self._max_jobs} job listings from German job boards. "
            "Return results as a JSON array where each element has the fields: "
            "title, company, location, salary_min (integer or null), salary_max (integer or null), "
            "work_type, job_board, job_url."
        )
        return f"{' '.join(query_parts)} ({site_clause}). {instruction}"

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
                return self._client.messages.create(**kwargs)
            except anthropic.APIStatusError as exc:
                if attempt == 2:
                    raise
                wait = 2**attempt
                logger.warning("API error (attempt %d): %s — retrying in %ds", attempt + 1, exc, wait)
                time.sleep(wait)
        raise RuntimeError("unreachable")

    def _claude_web_search(self, query: str) -> str:
        tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]
        messages = [{"role": "user", "content": f"Search for jobs: {query}"}]
        response = self._make_api_call(messages, tools=tools)
        return "\n\n".join(
            block.text for block in response.content if block.type == "text"
        )

    def _parse_results(self, raw_response: str, params: JobSearchParams) -> list[JobListing]:
        if not raw_response.strip():
            return []

        prompt = (
            "Extract job listings from the following text and return ONLY a JSON array "
            "(no markdown fences, no prose). Each element must have these fields: "
            "title, company, location, salary_min (integer or null), salary_max (integer or null), "
            "work_type, job_board, job_url.\n\n"
            f"Text:\n{raw_response}"
        )
        messages = [{"role": "user", "content": prompt}]
        response = self._make_api_call(messages)
        text = "\n".join(block.text for block in response.content if block.type == "text")

        # Strip accidental markdown fences
        text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Failed to parse JSON from Claude response; raw: %.200s", text)
            return []

        if not isinstance(data, list):
            logger.warning("Expected JSON array, got %s", type(data).__name__)
            return []

        listings = []
        for item in data:
            listing = self._listing_from_dict(item)
            if listing:
                listings.append(listing)
        return listings

    def _listing_from_dict(self, data: dict) -> Optional[JobListing]:
        title = data.get("title") or ""
        if not title:
            return None

        salary_raw = data.get("salary_min"), data.get("salary_max")
        if isinstance(salary_raw[0], str) or isinstance(salary_raw[1], str):
            sal_str = f"{salary_raw[0] or ''} {salary_raw[1] or ''}".strip()
            salary_min, salary_max = self._normalize_salary(sal_str)
        else:
            salary_min = int(salary_raw[0]) if salary_raw[0] is not None else None
            salary_max = int(salary_raw[1]) if salary_raw[1] is not None else None

        return JobListing(
            title=str(title),
            company=str(data.get("company") or ""),
            location=str(data.get("location") or ""),
            salary_min=salary_min,
            salary_max=salary_max,
            work_type=str(data.get("work_type") or ""),
            job_board=str(data.get("job_board") or ""),
            job_url=str(data.get("job_url") or ""),
        )

    def _normalize_salary(self, salary_str: str) -> tuple[Optional[int], Optional[int]]:
        if not salary_str or not salary_str.strip():
            return None, None

        # Replace k/K with 000
        salary_str = re.sub(r"(\d+)\s*[kK]", lambda m: str(int(m.group(1)) * 1000), salary_str)

        # Extract numeric tokens (handle European dot-separator and comma-separator)
        # Remove currency symbols and non-numeric noise first
        cleaned = re.sub(r"[€$£]", "", salary_str)
        # European thousands: 80.000 → treat dots between digits as thousands sep
        cleaned = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1\2", cleaned)
        # US/EN thousands commas: 80,000
        cleaned = cleaned.replace(",", "")

        numbers = re.findall(r"\d+", cleaned)
        if not numbers:
            return None, None

        try:
            if len(numbers) >= 2:
                return int(numbers[0]), int(numbers[1])
            return int(numbers[0]), None
        except ValueError:
            return None, None

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
