"""Tests for the job store — what is new, what is returning, what persists."""

from datetime import date
from pathlib import Path

import pytest

from job_research.analyzer import JobListing
from job_research.store import JobStore

DAY_ONE = date(2026, 8, 24)
DAY_TWO = date(2026, 8, 25)


@pytest.fixture
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.db")


def _listing(title="AI Engineer", company="Acme", location="Berlin", **kwargs) -> JobListing:
    return JobListing(title=title, company=company, location=location, **kwargs)


# ------------------------------------------------------------------ new/returning


def test_first_run_reports_everything_as_new(store):
    diff = store.record([_listing(), _listing(title="ML Engineer")], today=DAY_ONE)
    assert len(diff.new) == 2
    assert diff.returning == []


def test_second_run_reports_the_same_listings_as_returning(store):
    listings = [_listing(), _listing(title="ML Engineer")]
    store.record(listings, today=DAY_ONE)

    diff = store.record(listings, today=DAY_TWO)

    assert diff.new == []
    assert len(diff.returning) == 2


def test_only_the_unseen_listing_is_new_on_a_later_run(store):
    store.record([_listing()], today=DAY_ONE)

    diff = store.record([_listing(), _listing(title="ML Engineer")], today=DAY_TWO)

    assert [lst.title for lst in diff.new] == ["ML Engineer"]
    assert [lst.title for lst in diff.returning] == ["AI Engineer"]


def test_the_same_job_twice_in_one_run_is_new_only_once(store):
    """Dedup should have caught this, but the store must not double-count either."""
    diff = store.record([_listing(), _listing()], today=DAY_ONE)
    assert len(diff.new) == 1
    assert len(diff.returning) == 1
    assert store.count() == 1


def test_recording_nothing_is_harmless(store):
    diff = store.record([], today=DAY_ONE)
    assert diff.total == 0
    assert store.count() == 0


def test_a_job_reworded_by_another_source_is_not_new_again(store):
    """The reason the id is content-derived rather than URL-derived."""
    store.record(
        [_listing(title="AI Engineer", location="Berlin", job_url="https://indeed/1")],
        today=DAY_ONE,
    )

    diff = store.record(
        [
            _listing(
                title="AI Engineer (m/w/d)",
                location="Berlin, Germany",
                job_url="https://arbeitsagentur/2",
            )
        ],
        today=DAY_TWO,
    )

    assert diff.new == []


# ---------------------------------------------------------------- persistence


def test_first_seen_survives_a_later_sighting(store):
    """It answers "how long has this been open", so re-seeing must not reset it."""
    store.record([_listing()], today=DAY_ONE)
    store.record([_listing()], today=DAY_TWO)

    assert store.first_seen(_listing().job_id) == DAY_ONE


def test_mutable_fields_are_refreshed_on_a_later_sighting(store):
    store.record([_listing(salary_min=60000, salary_max=70000)], today=DAY_ONE)
    store.record([_listing(salary_min=65000, salary_max=80000)], today=DAY_TWO)

    with store._connect() as conn:
        row = conn.execute("SELECT salary_min, salary_max, last_seen FROM jobs").fetchone()

    assert (row["salary_min"], row["salary_max"]) == (65000, 80000)
    assert row["last_seen"] == DAY_TWO.isoformat()


def test_the_store_survives_being_reopened(store, tmp_path):
    """Nothing is useful across runs if it only lives in memory."""
    store.record([_listing()], today=DAY_ONE)

    reopened = JobStore(tmp_path / "jobs.db")

    assert reopened.count() == 1
    diff = reopened.record([_listing()], today=DAY_TWO)
    assert diff.new == []


def test_opening_a_store_creates_missing_directories(tmp_path):
    store = JobStore(tmp_path / "nested" / "deeper" / "jobs.db")
    assert store.count() == 0


def test_known_ids_reports_what_has_been_recorded(store):
    store.record([_listing(), _listing(title="ML Engineer")], today=DAY_ONE)
    assert store.known_ids() == {_listing().job_id, _listing(title="ML Engineer").job_id}


def test_first_seen_of_an_unknown_job_is_none(store):
    assert store.first_seen("never-recorded-00000000") is None


def test_a_listing_without_a_date_is_stored(store):
    """posted_date is optional and must not block persistence."""
    store.record([_listing(posted_date=None)], today=DAY_ONE)
    assert store.count() == 1


def test_posted_date_round_trips_as_iso(store):
    store.record([_listing(posted_date=date(2026, 8, 20))], today=DAY_ONE)
    with store._connect() as conn:
        assert conn.execute("SELECT posted_date FROM jobs").fetchone()[0] == "2026-08-20"


# ------------------------------------------------------------------ collisions


def test_a_hash_collision_is_reported_rather_than_silently_merged(store, monkeypatch, caplog):
    """Two different postings sharing an id must not be quietly treated as one."""
    store.record([_listing(title="AI Engineer")], today=DAY_ONE)

    # Capture the target id before patching, or the property recurses into itself.
    shared_id = _listing().job_id
    colliding = _listing(title="Totally Different Role")
    monkeypatch.setattr(type(colliding), "job_id", property(lambda self: shared_id))

    with caplog.at_level("WARNING"):
        diff = store.record([colliding], today=DAY_TWO)

    assert diff.new == []  # treated as known, but...
    assert "collision" in caplog.text  # ...loudly
