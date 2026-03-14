#!/usr/bin/env python3
"""Evaluate search result quality by comparing Claude's output against web_search URLs.

Usage:
    uv run python scripts/eval_search_quality.py "AI Engineer" "Berlin"
    uv run python scripts/eval_search_quality.py "Data Scientist" "Munich" --work-type "Remote only"

Requires CLAUDE_API_KEY in environment or .env file.
"""

import argparse
import re
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add src to path so we can import job_research
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_research.boards import get_adapter
from job_research.config import Config, JobSearchParams, WorkType
from job_research.scraper import ClaudeScraper


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Evaluate search result quality")
    parser.add_argument("keywords", help="Job search keywords")
    parser.add_argument("location", help="Job location")
    parser.add_argument("--work-type", default="Any", help="Work type filter")
    args = parser.parse_args()

    config = Config.from_env()
    if not config.claude_api_key:
        print("ERROR: CLAUDE_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    scraper = ClaudeScraper(
        api_key=config.claude_api_key,
        model=config.claude_model,
        max_jobs=config.max_jobs_per_search,
        board_config=config.job_boards,
    )

    params = JobSearchParams(
        keywords=args.keywords,
        location=args.location,
        work_type=WorkType(args.work_type),
    )
    query = scraper._build_search_query(params)

    print(f"Query: {query}")
    print(f"Boards: {scraper._boards}")
    print()

    # Make the API call directly to inspect raw response
    tools = [{
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 10,
        "allowed_domains": scraper._boards,
        "user_location": {"type": "approximate", "country": "DE"},
    }]
    system = scraper._build_system_prompt()
    user_message = f"Search for {query} job listings and extract what you find"
    messages = [{"role": "user", "content": user_message}]

    response = scraper._make_api_call(messages, tools=tools, system=system)

    # Extract ground-truth URLs
    search_urls = scraper._extract_search_result_urls(response)
    adapters = [get_adapter(d) for d in scraper._boards]

    print(f"=== Ground-truth URLs from web_search ({len(search_urls)}) ===")
    job_urls = 0
    search_page_urls = 0
    for url in sorted(search_urls):
        is_job = any(a.is_job_listing_url(url) for a in adapters)
        label = "JOB" if is_job else "SEARCH-PAGE"
        if is_job:
            job_urls += 1
        else:
            search_page_urls += 1
        print(f"  [{label}] {url}")
    print(f"  → {job_urls} individual job URLs, {search_page_urls} search/category page URLs")
    print()

    # Extract Claude's JSON output
    raw_text = "\n\n".join(
        block.text for block in response.content if block.type == "text"
    )
    text = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()
    data = scraper._extract_json(text)

    # Debug: show raw response preview
    print("=== Raw response preview (first 2000 chars) ===")
    print(raw_text[:2000])
    if len(raw_text) > 2000:
        print(f"  ... ({len(raw_text) - 2000} more chars)")
    print()

    if data is None:
        print("WARNING: Response was not JSON, sending follow-up extraction request...")
        follow_up_messages = [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": raw_text},
            {"role": "user", "content": (
                "Now output ONLY the JSON array of job listings you found. "
                "No commentary, no markdown fences — just the raw JSON array."
            )},
        ]
        retry_response = scraper._make_api_call(
            follow_up_messages, max_tokens=4096, system=system
        )
        retry_text = "\n\n".join(
            block.text for block in retry_response.content if block.type == "text"
        )
        retry_text = re.sub(r"```(?:json)?\s*", "", retry_text).strip().rstrip("`").strip()
        data = scraper._extract_json(retry_text)
        if data is None:
            print("ERROR: Could not parse JSON from response after retry")
            print(f"Raw text: {raw_text[:500]}")
            sys.exit(1)

    print(f"=== Claude's output ({len(data)} listings) ===")
    normalized_search = {scraper._normalize_url(u) for u in search_urls}

    matched = 0
    search_page = 0
    fabricated = 0

    for item in data:
        url = item.get("job_url", "")
        norm = scraper._normalize_url(url) if url else ""
        in_search = norm in normalized_search
        is_job = any(a.is_job_listing_url(url) for a in adapters) if url else False

        if in_search and is_job:
            status = "VALID"
            matched += 1
        elif in_search:
            status = "SEARCH-PAGE"
            search_page += 1
        else:
            status = "FABRICATED"
            fabricated += 1

        title = item.get("title", "?")[:50]
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        salary = f"€{salary_min}-{salary_max}" if salary_min else "no salary"
        print(f"  [{status}] {title} | {salary}")
        print(f"           {url}")

    print()
    print("=== Summary ===")
    total = matched + search_page + fabricated
    match_rate = (matched / total * 100) if total else 0
    print(f"  Web search result URLs:  {len(search_urls)} ({job_urls} job, {search_page_urls} search-page)")
    print(f"  Claude output listings:  {total}")
    print(f"  Valid (job URL + in search): {matched}/{total} ({match_rate:.0f}%)")
    print(f"  Search-page URLs:        {search_page}")
    print(f"  Fabricated:              {fabricated}")

    # Show missed valid job URLs
    valid_ground_truth = {
        url for url in search_urls
        if any(a.is_job_listing_url(url) for a in adapters)
    }
    claude_urls = {item.get("job_url", "") for item in data}
    missed = valid_ground_truth - claude_urls
    if missed:
        print(f"\n=== Missed valid job URLs ({len(missed)}) ===")
        for url in sorted(missed):
            print(f"  {url}")

    # Field coverage
    has_salary = sum(1 for d in data if d.get("salary_min") is not None)
    has_company = sum(1 for d in data if d.get("company"))
    has_location = sum(1 for d in data if d.get("location"))
    print(f"  With salary:             {has_salary}/{total}")
    print(f"  With company:            {has_company}/{total}")
    print(f"  With location:           {has_location}/{total}")


if __name__ == "__main__":
    main()
