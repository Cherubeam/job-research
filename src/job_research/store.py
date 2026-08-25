"""Persistent record of every posting this tool has seen.

The point of the store is one question: *which of these did I not see last time?*
Everything else it holds is in service of answering that across runs.

SQLite, from the standard library — no new dependency, and it tolerates the
concurrent reads a Gradio session produces better than a JSON file would. A
connection is opened per operation rather than held: searches run on a
background thread, and sqlite3 connections are not shareable across threads.

**What it deliberately does not track: disappearance.** A posting absent from
today's results has not necessarily been withdrawn — it may simply not match
today's query. Reporting "gone" would need per-query history, so the store
reports *new* and *returning* and stays quiet about the rest rather than saying
something it cannot support.
"""

import logging
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from job_research.analyzer import JobListing
from job_research.identity import identity_key

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    identity     TEXT NOT NULL,
    title        TEXT NOT NULL,
    company      TEXT NOT NULL,
    location     TEXT NOT NULL,
    job_board    TEXT NOT NULL DEFAULT '',
    job_url      TEXT NOT NULL DEFAULT '',
    salary_min   INTEGER,
    salary_max   INTEGER,
    work_type    TEXT NOT NULL DEFAULT '',
    posted_date  TEXT,
    first_seen   TEXT NOT NULL,
    last_seen    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_first_seen ON jobs(first_seen);
"""

_IDENTITY_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class RunDiff:
    """What one search run added to, or re-confirmed in, the store."""

    new: list[JobListing] = field(default_factory=list)
    returning: list[JobListing] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.new) + len(self.returning)


class JobStore:
    """Records postings by their stable `job_id` and reports what is new."""

    def __init__(self, path: Path) -> None:
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, listings: list[JobListing], *, today: date | None = None) -> RunDiff:
        """Record *listings*, returning which were new and which were already known.

        Re-seeing a posting refreshes `last_seen` and the fields that can change
        between runs (salary, work type, URL); `first_seen` is never touched,
        because it is the answer to "how long has this been open".
        """
        seen_on = (today or date.today()).isoformat()
        new: list[JobListing] = []
        returning: list[JobListing] = []

        with self._connect() as conn:
            known = {
                row["job_id"]: row["identity"]
                for row in conn.execute("SELECT job_id, identity FROM jobs")
            }
            for listing in listings:
                job_id = listing.job_id
                identity = _IDENTITY_SEPARATOR.join(
                    identity_key(listing.title, listing.company, listing.location)
                )

                if job_id in known:
                    if known[job_id] != identity:
                        # Two different postings hashed to one id. Report it
                        # rather than silently merging them.
                        logger.warning(
                            "job_id collision on %s: stored %r vs incoming %r",
                            job_id,
                            known[job_id],
                            identity,
                        )
                    returning.append(listing)
                    conn.execute(
                        """
                        UPDATE jobs
                           SET last_seen = ?, job_url = ?, salary_min = ?,
                               salary_max = ?, work_type = ?, job_board = ?
                         WHERE job_id = ?
                        """,
                        (
                            seen_on,
                            listing.job_url,
                            listing.salary_min,
                            listing.salary_max,
                            listing.work_type,
                            listing.job_board,
                            job_id,
                        ),
                    )
                else:
                    new.append(listing)
                    known[job_id] = identity  # a run can contain the same job twice
                    conn.execute(
                        """
                        INSERT INTO jobs (
                            job_id, identity, title, company, location, job_board,
                            job_url, salary_min, salary_max, work_type, posted_date,
                            first_seen, last_seen
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            job_id,
                            identity,
                            listing.title,
                            listing.company,
                            listing.location,
                            listing.job_board,
                            listing.job_url,
                            listing.salary_min,
                            listing.salary_max,
                            listing.work_type,
                            listing.posted_date.isoformat() if listing.posted_date else None,
                            seen_on,
                            seen_on,
                        ),
                    )

        logger.info("Store: %d new, %d already known", len(new), len(returning))
        return RunDiff(new=new, returning=returning)

    def known_ids(self) -> set[str]:
        with self._connect() as conn:
            return {row["job_id"] for row in conn.execute("SELECT job_id FROM jobs")}

    def first_seen(self, job_id: str) -> date | None:
        """When this posting first showed up, or None if it never has."""
        with self._connect() as conn:
            row = conn.execute("SELECT first_seen FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        return date.fromisoformat(row["first_seen"]) if row else None

    def count(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM jobs").fetchone()["n"])
