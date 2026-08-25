#!/usr/bin/env python
"""Manual probe for the Bundesagentur Jobsuche endpoint.

Run this by hand to check that the endpoint still answers and that the field
names this project maps have not moved. BA's API is unofficial and has changed
without notice before — `pc/v4` was retired server-side on 2026-08-04 — so the
test suite runs against recorded fixtures and this script is the only thing that
touches the network.

It stays manual on purpose: ADR-001 permits bounded, user-initiated queries, not
scheduled ones.

    uv run python scripts/probe_bundesagentur.py "AI Engineer" --where Berlin

Add --json to dump the first raw posting, which is what you want when a field
has been renamed.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from job_research.sources.bundesagentur import (  # noqa: E402
    BASE_URL,
    JobsucheClient,
    to_job_listing,
)

# Fields every posting must carry. A missing one means the mapping is stale.
REQUIRED_FIELDS = (
    "stellenangebotsTitel",
    "firma",
    "stellenlokationen",
    "referenznummer",
    "datumErsteVeroeffentlichung",
)

# Present only on some postings — BA omits these rather than sending false/empty.
# Their absence is normal and must not read as a failure.
OPTIONAL_FIELDS = (
    "homeofficemoeglich",
    "verguetungsangabe",
    "arbeitszeitVollzeit",
    "externeURL",
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("keywords", nargs="?", default="AI Engineer")
    parser.add_argument("--where", default=None, help="City or region")
    parser.add_argument("--days", type=int, default=None, help="Published within N days")
    parser.add_argument("--size", type=int, default=5, help="Postings to fetch (default 5)")
    parser.add_argument("--json", action="store_true", help="Dump the first raw posting")
    args = parser.parse_args()

    print(f"Endpoint: {BASE_URL}/jobs")
    print(f"Query:    was={args.keywords!r} wo={args.where!r} days={args.days}\n")

    client = JobsucheClient()
    postings, total = client.search(
        what=args.keywords,
        where=args.where,
        published_since_days=args.days,
        size=args.size,
    )
    print(f"maxErgebnisse: {total}")
    print(f"returned:      {len(postings)}\n")

    if not postings:
        print("No postings returned — nothing to check the field mapping against.")
        return 1

    # Required fields are checked across every posting: BA omits optional ones
    # per-posting, so judging from a single sample gives false alarms.
    print("Required fields (checked across all returned postings):")
    missing = [f for f in REQUIRED_FIELDS if not all(f in p for p in postings)]
    for field in REQUIRED_FIELDS:
        present = sum(1 for p in postings if field in p)
        mark = "ok " if present == len(postings) else "MISSING"
        print(f"  [{mark}] {field}  ({present}/{len(postings)})")

    print("\nOptional fields (absence is normal):")
    for field in OPTIONAL_FIELDS:
        present = sum(1 for p in postings if field in p)
        print(f"  [   ] {field}  ({present}/{len(postings)})")

    known = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    unexpected = sorted({k for p in postings for k in p} - known)
    if unexpected:
        print(f"\nOther fields returned: {', '.join(unexpected)}")

    print("\nMapped listings:")
    for posting in postings:
        listing = to_job_listing(posting)
        if listing is None:
            print("  <no usable title>")
            continue
        print(f"  {listing.title}")
        print(f"    company:  {listing.company or '-'}")
        print(f"    location: {listing.location or '-'}")
        print(f"    posted:   {listing.posted_date or '-'}")
        print(f"    salary:   {listing.salary_min or '-'} - {listing.salary_max or '-'}")
        print(f"    type:     {listing.work_type or '-'}")
        print(f"    url:      {listing.job_url or '-'}")

    if args.json:
        print("\nRaw first posting:")
        print(json.dumps(postings[0], indent=2, ensure_ascii=False))

    if missing:
        print(f"\nFAIL: {len(missing)} required field(s) missing — update the mapping.")
        return 1
    print("\nOK: every required field is present on every posting.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
