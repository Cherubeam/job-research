#!/usr/bin/env python3
"""Evaluate IndeedDirectScraper result quality and optionally compare with Claude scraper.

Usage:
    uv run python scripts/eval_direct_scraper.py "AI Engineer" "Berlin"
    uv run python scripts/eval_direct_scraper.py "Data Scientist" "Munich" --work-type "Remote only"

Set CLAUDE_API_KEY to also run the Claude scraper for side-by-side comparison.
"""

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_research.config import Config, JobSearchParams, WorkType
from job_research.indeed import IndeedDirectScraper


def _field_coverage(listings: list) -> dict[str, int]:
    return {
        "salary": sum(1 for x in listings if x.salary_min is not None),
        "company": sum(1 for x in listings if x.company),
        "location": sum(1 for x in listings if x.location),
        "description": sum(1 for x in listings if x.description),
        "job_url": sum(1 for x in listings if x.job_url),
        "posted_date": sum(1 for x in listings if x.posted_date),
    }


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="Evaluate IndeedDirectScraper quality")
    parser.add_argument("keywords", help="Job search keywords")
    parser.add_argument("location", help="Job location")
    parser.add_argument("--work-type", default="Any", help="Work type filter")
    parser.add_argument("--max-jobs", type=int, default=20, help="Max results")
    args = parser.parse_args()

    config = Config.from_env()
    params = JobSearchParams(
        keywords=args.keywords,
        location=args.location,
        work_type=WorkType(args.work_type),
    )

    # --- Indeed Direct ---
    print("=" * 60)
    print("IndeedDirectScraper")
    print("=" * 60)

    scraper = IndeedDirectScraper(max_jobs=args.max_jobs)
    cache_dir = Path("data/cache")
    cache_dir.mkdir(parents=True, exist_ok=True)

    try:
        listings = scraper.search_jobs(params, cache_dir, cache_duration_hours=0)
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    print(f"\nFound {len(listings)} listings\n")

    # Field coverage
    coverage = _field_coverage(listings)
    total = len(listings)
    print("--- Field coverage ---")
    for field, count in coverage.items():
        pct = (count / total * 100) if total else 0
        print(f"  {field:15s}: {count}/{total} ({pct:.0f}%)")

    # Sample listings
    print("\n--- Sample listings (first 5) ---")
    for i, listing in enumerate(listings[:5], 1):
        salary = (
            f"€{listing.salary_min}-{listing.salary_max}"
            if listing.salary_min
            else "no salary"
        )
        desc_preview = (listing.description[:80] + "...") if listing.description else "(none)"
        print(f"  {i}. {listing.title}")
        print(f"     {listing.company} | {listing.location} | {salary}")
        print(f"     {listing.job_url}")
        print(f"     {desc_preview}")
        print()

    # --- Claude comparison (optional) ---
    if config.claude_api_key:
        print("=" * 60)
        print("ClaudeScraper (comparison)")
        print("=" * 60)

        from job_research.scraper import ClaudeScraper

        claude_scraper = ClaudeScraper(
            api_key=config.claude_api_key,
            model=config.claude_model,
            max_jobs=args.max_jobs,
            board_config=config.job_boards,
        )
        try:
            claude_listings = claude_scraper.search_jobs(
                params, cache_dir, cache_duration_hours=0
            )
        except RuntimeError as exc:
            print(f"ERROR: {exc}")
            return

        print(f"\nFound {len(claude_listings)} listings\n")
        claude_coverage = _field_coverage(claude_listings)
        claude_total = len(claude_listings)
        print("--- Field coverage ---")
        for field, count in claude_coverage.items():
            pct = (count / claude_total * 100) if claude_total else 0
            print(f"  {field:15s}: {count}/{claude_total} ({pct:.0f}%)")

        # Side-by-side summary
        print(f"\n{'=' * 60}")
        print("Side-by-side summary")
        print(f"{'=' * 60}")
        print(f"  {'':15s}  Indeed   Claude")
        print(f"  {'Listings':15s}  {total:<8d} {claude_total}")
        for field in coverage:
            i_count = coverage[field]
            c_count = claude_coverage[field]
            print(f"  {field:15s}  {i_count:<8d} {c_count}")
    else:
        print("\n(Set CLAUDE_API_KEY to also run Claude scraper for comparison)")


if __name__ == "__main__":
    main()
