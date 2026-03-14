#!/usr/bin/env python3
"""Evaluate search result quality by comparing Claude's output against web_search URLs.

Usage:
    uv run python scripts/eval_search_quality.py "AI Engineer" "Berlin"
    uv run python scripts/eval_search_quality.py "Data Scientist" "Munich" --work-type "Remote only"

Requires CLAUDE_API_KEY in environment or .env file.
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

# Add src to path so we can import job_research
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

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
    system = (
        "You are a job search assistant. Search German job boards using the "
        "web_search tool. Then extract job listings ONLY from the search results "
        "you received — never invent or fabricate listings.\n\n"
        "Return a JSON array (no markdown fences, no commentary). Each element:\n"
        "  title (string), company (string), location (string),\n"
        "  salary_min (integer or null), salary_max (integer or null),\n"
        "  work_type (string), job_board (string), job_url (string).\n\n"
        "Rules:\n"
        "- Use the EXACT URL from the search result for job_url.\n"
        "- Set salary fields to null unless the search result explicitly states a salary.\n"
        "- If you found fewer listings, return fewer. Do not pad results.\n"
        "- Only include results that are individual job postings, not search result pages."
    )
    user_message = f"Search for {query} job listings and extract what you find"
    messages = [{"role": "user", "content": user_message}]

    import re

    response = scraper._make_api_call(messages, tools=tools, system=system)

    # Extract ground-truth URLs
    search_urls = scraper._extract_search_result_urls(response)
    print(f"=== Ground-truth URLs from web_search ({len(search_urls)}) ===")
    for url in sorted(search_urls):
        print(f"  {url}")
    print()

    # Extract Claude's JSON output
    raw_text = "\n\n".join(
        block.text for block in response.content if block.type == "text"
    )
    text = re.sub(r"```(?:json)?\s*", "", raw_text).strip().rstrip("`").strip()
    data = scraper._extract_json(text)

    if data is None:
        print("ERROR: Could not parse JSON from response")
        print(f"Raw text: {raw_text[:500]}")
        sys.exit(1)

    print(f"=== Claude's output ({len(data)} listings) ===")
    matched = 0
    unmatched = 0
    normalized_search = {scraper._normalize_url(u) for u in search_urls}

    for item in data:
        url = item.get("job_url", "")
        norm = scraper._normalize_url(url) if url else ""
        is_match = norm in normalized_search
        status = "MATCH" if is_match else "FABRICATED"
        if is_match:
            matched += 1
        else:
            unmatched += 1
        title = item.get("title", "?")[:50]
        salary_min = item.get("salary_min")
        salary_max = item.get("salary_max")
        salary = f"€{salary_min}-{salary_max}" if salary_min else "no salary"
        print(f"  [{status}] {title} | {salary}")
        print(f"           {url}")

    print()
    print("=== Summary ===")
    total = matched + unmatched
    match_rate = (matched / total * 100) if total else 0
    print(f"  Web search result URLs:  {len(search_urls)}")
    print(f"  Claude output listings:  {total}")
    print(f"  URL match rate:          {matched}/{total} ({match_rate:.0f}%)")
    print(f"  Fabricated:              {unmatched}")

    # Field coverage
    has_salary = sum(1 for d in data if d.get("salary_min") is not None)
    has_company = sum(1 for d in data if d.get("company"))
    has_location = sum(1 for d in data if d.get("location"))
    print(f"  With salary:             {has_salary}/{total}")
    print(f"  With company:            {has_company}/{total}")
    print(f"  With location:           {has_location}/{total}")


if __name__ == "__main__":
    main()
