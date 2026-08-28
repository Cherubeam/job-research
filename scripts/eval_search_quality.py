#!/usr/bin/env python3
"""Compare what the LLM backend *reports* against what its web search actually returned.

The scraper discards any listing whose URL is not in the search results, so the
interesting number is not "how many listings" but "how many survived
validation, and what was thrown away". This prints both sides.

Usage:
    uv run python scripts/eval_search_quality.py "AI Engineer" "Berlin"
    uv run python scripts/eval_search_quality.py "Data Scientist" "Munich" --work-type "Remote only"

Uses whichever provider `LLM_PROVIDER` selects, so it needs that provider's key
(`OPENROUTER_API_KEY` by default, `CLAUDE_API_KEY` for `anthropic`).
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add src to path so we can import job_research
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_research.config import Config, JobSearchParams, LLMProvider, WorkType
from job_research.providers import AnthropicProvider, OpenRouterProvider, SearchProvider
from job_research.scraper import MAX_SEARCHES, LLMScraper
from job_research.sources import Backend, catalog


def _provider(config: Config) -> SearchProvider:
    """Build the configured provider, or exit with the variable to set."""
    if config.llm_provider is LLMProvider.OPENROUTER:
        if not config.openrouter_api_key:
            print("ERROR: OPENROUTER_API_KEY not set", file=sys.stderr)
            sys.exit(1)
        return OpenRouterProvider(
            api_key=config.openrouter_api_key,
            model=config.openrouter_model,
            max_results=config.openrouter_search_results,
            engine=config.openrouter_search_engine,
        )
    if not config.claude_api_key:
        print("ERROR: CLAUDE_API_KEY not set", file=sys.stderr)
        sys.exit(1)
    return AnthropicProvider(api_key=config.claude_api_key, model=config.claude_model)


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Evaluate search result quality")
    parser.add_argument("keywords", help="Job search keywords")
    parser.add_argument("location", help="Job location")
    parser.add_argument("--work-type", default="Any", help="Work type filter")
    args = parser.parse_args()

    config = Config.from_env()
    provider = _provider(config)
    scraper = LLMScraper(provider, max_jobs=config.max_jobs_per_search)

    params = JobSearchParams(
        keywords=args.keywords,
        location=args.location,
        work_type=WorkType(args.work_type),
    )
    sources = catalog.resolve(params.enabled_sources, Backend.LLM)
    if not sources:
        print(
            "ERROR: no enabled source is reachable by the LLM backend. "
            f"Set ENABLED_SOURCES to include one of: "
            f"{', '.join(s.id for s in catalog.for_backend(Backend.LLM))}",
            file=sys.stderr,
        )
        sys.exit(1)

    query = scraper._build_search_query(params)
    print(f"Provider: {provider.name} ({provider.model})")
    print(f"Query: {query}")
    print(f"Sources: {', '.join(s.id for s in sources)}")
    print()

    system = scraper._build_system_prompt(sources)
    user_message = f"Search for {query} job listings and extract what you find"
    response = provider.search(
        system=system,
        messages=[{"role": "user", "content": user_message}],
        allowed_domains=[s.domain for s in sources],
        max_searches=MAX_SEARCHES,
    )

    print(f"=== Ground-truth URLs from web search ({len(response.result_urls)}) ===")
    job_urls = 0
    for url in sorted(response.result_urls):
        is_job = any(s.is_job_listing_url(url) for s in sources)
        job_urls += is_job
        print(f"  [{'JOB' if is_job else 'SEARCH-PAGE'}] {url}")
    print(
        f"  → {job_urls} individual job URLs, "
        f"{len(response.result_urls) - job_urls} search/category page URLs"
    )
    print()

    print("=== Raw response preview (first 2000 chars) ===")
    print(response.text[:2000])
    if len(response.text) > 2000:
        print(f"  ... ({len(response.text) - 2000} more chars)")
    print()

    data = scraper._extract_json(scraper._strip_fences(response.text))
    if data is None:
        print("ERROR: could not parse a JSON array from the response", file=sys.stderr)
        sys.exit(1)

    normalized_search = {scraper._normalize_url(u) for u in response.result_urls}
    print(f"=== Model output ({len(data)} listings) ===")
    fabricated = 0
    for item in data:
        url = item.get("job_url") if isinstance(item, dict) else None
        if not url:
            label = "NO-URL"
        elif scraper._normalize_url(url) not in normalized_search:
            label = "FABRICATED"
            fabricated += 1
        elif not any(s.is_job_listing_url(url) for s in sources):
            label = "SEARCH-PAGE"
        else:
            label = "OK"
        title = item.get("title", "?") if isinstance(item, dict) else "?"
        print(f"  [{label}] {title} — {url}")

    print()
    print(f"Summary: {len(data)} reported, {fabricated} with URLs never seen in search results")


if __name__ == "__main__":
    main()
