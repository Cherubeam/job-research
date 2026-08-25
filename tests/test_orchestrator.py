"""Tests for multi-source orchestration — assignment, fan-out, and health."""

import threading
from pathlib import Path

import pytest

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams
from job_research.orchestrator import Orchestrator, assign_backends
from job_research.sources import Backend, catalog

ALL = {Backend.JOBSPY, Backend.BUNDESAGENTUR, Backend.CLAUDE}


def _sources(*ids: str) -> tuple:
    return tuple(catalog.get(i) for i in ids)


# ---------------------------------------------------------------- assignment


def test_each_source_goes_to_a_backend_that_can_reach_it():
    assignments, skipped = assign_backends(_sources("indeed", "arbeitsagentur"), ALL)

    assert skipped == []
    assert {s.id for s in assignments[Backend.JOBSPY]} == {"indeed"}
    assert {s.id for s in assignments[Backend.BUNDESAGENTUR]} == {"arbeitsagentur"}


def test_the_preferred_backend_wins_where_it_can_serve_the_source():
    """SCRAPER_BACKEND must still mean something."""
    assignments, _ = assign_backends(_sources("indeed"), ALL, preferred=Backend.CLAUDE)
    assert Backend.CLAUDE in assignments
    assert Backend.JOBSPY not in assignments


def test_the_preferred_backend_is_ignored_where_it_cannot_serve_the_source():
    assignments, skipped = assign_backends(
        _sources("arbeitsagentur"), ALL, preferred=Backend.JOBSPY
    )
    assert skipped == []
    assert Backend.BUNDESAGENTUR in assignments


def test_free_backends_are_preferred_over_the_metered_one():
    """Claude costs money per search, so it must not be a silent default route."""
    assignments, _ = assign_backends(_sources("indeed", "arbeitsagentur"), ALL)
    assert Backend.CLAUDE not in assignments


def test_claude_is_used_when_it_is_the_only_backend_that_can_reach_a_source():
    assignments, skipped = assign_backends(_sources("stepstone"), ALL)
    assert skipped == []
    assert {s.id for s in assignments[Backend.CLAUDE]} == {"stepstone"}


def test_an_unreachable_source_is_skipped_with_a_reason():
    """Without an API key, StepStone has no route — say so, do not drop it."""
    assignments, skipped = assign_backends(
        _sources("stepstone"), {Backend.JOBSPY, Backend.BUNDESAGENTUR}
    )
    assert assignments == {}
    assert len(skipped) == 1
    assert "claude" in skipped[0].skipped
    assert not skipped[0].ok


def test_several_sources_can_share_one_backend():
    assignments, _ = assign_backends(_sources("indeed", "linkedin"), ALL)
    assert {s.id for s in assignments[Backend.JOBSPY]} == {"indeed", "linkedin"}


# ------------------------------------------------------------------ fan-out


class FakeScraper:
    """Returns fixed listings, recording the params it was called with."""

    def __init__(self, listings=None, error: Exception | None = None) -> None:
        self.listings = listings or []
        self.error = error
        self.calls: list[JobSearchParams] = []
        self.lock = threading.Lock()

    def search_jobs(self, params, cache_dir, cache_duration_hours=24):
        with self.lock:
            self.calls.append(params)
        if self.error:
            raise self.error
        return list(self.listings)


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    return tmp_path / "cache"


def _params(*source_ids: str) -> JobSearchParams:
    return JobSearchParams(keywords="AI Engineer", enabled_sources=list(source_ids))


def test_results_from_every_backend_are_merged(cache_dir):
    jobspy = FakeScraper([JobListing(title="From Indeed", company="A")])
    ba = FakeScraper([JobListing(title="From BA", company="B")])
    orchestrator = Orchestrator({Backend.JOBSPY: jobspy, Backend.BUNDESAGENTUR: ba})

    outcome = orchestrator.search(_params("indeed", "arbeitsagentur"), cache_dir)

    assert {lst.title for lst in outcome.listings} == {"From Indeed", "From BA"}


def test_each_backend_only_receives_the_sources_it_was_assigned(cache_dir):
    """A backend must not be asked for a board it cannot reach."""
    jobspy = FakeScraper([])
    ba = FakeScraper([])
    Orchestrator({Backend.JOBSPY: jobspy, Backend.BUNDESAGENTUR: ba}).search(
        _params("indeed", "arbeitsagentur"), cache_dir
    )

    assert jobspy.calls[0].enabled_sources == ["indeed"]
    assert ba.calls[0].enabled_sources == ["arbeitsagentur"]


def test_the_original_params_are_not_mutated(cache_dir):
    params = _params("indeed", "arbeitsagentur")
    Orchestrator({Backend.JOBSPY: FakeScraper([]), Backend.BUNDESAGENTUR: FakeScraper([])}).search(
        params, cache_dir
    )

    assert params.enabled_sources == ["indeed", "arbeitsagentur"]


def test_one_failing_backend_does_not_sink_the_search(cache_dir):
    """The whole point of per-source health: partial results beat no results."""
    working = FakeScraper([JobListing(title="From BA", company="B")])
    broken = FakeScraper(error=RuntimeError("indeed is down"))
    orchestrator = Orchestrator({Backend.JOBSPY: broken, Backend.BUNDESAGENTUR: working})

    outcome = orchestrator.search(_params("indeed", "arbeitsagentur"), cache_dir)

    assert [lst.title for lst in outcome.listings] == ["From BA"]
    assert len(outcome.failed) == 1
    assert "indeed is down" in outcome.failed[0].error


def test_a_failure_is_reported_per_source_not_per_backend(cache_dir):
    broken = FakeScraper(error=RuntimeError("boom"))
    outcome = Orchestrator({Backend.JOBSPY: broken}).search(
        _params("indeed", "linkedin"), cache_dir
    )
    assert {o.source.id for o in outcome.failed} == {"indeed", "linkedin"}


def test_counts_are_attributed_to_the_right_source(cache_dir):
    """One backend, two boards, one result list — counts split by job_board."""
    jobspy = FakeScraper(
        [
            JobListing(title="A", company="X", job_board="indeed"),
            JobListing(title="B", company="Y", job_board="indeed"),
            JobListing(title="C", company="Z", job_board="linkedin"),
        ]
    )
    outcome = Orchestrator({Backend.JOBSPY: jobspy}).search(
        _params("indeed", "linkedin"), cache_dir
    )

    counts = {o.source.id: o.count for o in outcome.outcomes}
    assert counts == {"indeed": 2, "linkedin": 1}


def test_summary_names_every_source(cache_dir):
    outcome = Orchestrator(
        {Backend.JOBSPY: FakeScraper([]), Backend.BUNDESAGENTUR: FakeScraper([])}
    ).search(_params("indeed", "arbeitsagentur"), cache_dir)

    summary = outcome.summary()
    assert "Indeed.de" in summary
    assert "Arbeitsagentur.de" in summary


def test_searching_nothing_returns_nothing_without_calling_a_backend(cache_dir):
    scraper = FakeScraper([JobListing(title="X", company="Y")])
    outcome = Orchestrator({Backend.JOBSPY: scraper}).search(_params(), cache_dir)

    assert outcome.listings == []
    assert outcome.outcomes == []
    assert scraper.calls == []


def test_a_search_with_only_unreachable_sources_reports_them(cache_dir):
    outcome = Orchestrator({Backend.JOBSPY: FakeScraper([])}).search(
        _params("stepstone"), cache_dir
    )
    assert outcome.listings == []
    assert outcome.outcomes[0].skipped
    assert outcome.succeeded == []


def test_backends_run_concurrently(cache_dir):
    """Two sources should not take twice as long as one."""
    barrier = threading.Barrier(2, timeout=10)

    class BlockingScraper(FakeScraper):
        def search_jobs(self, params, cache_dir, cache_duration_hours=24):
            barrier.wait()  # deadlocks unless both run at once
            return super().search_jobs(params, cache_dir, cache_duration_hours)

    orchestrator = Orchestrator(
        {Backend.JOBSPY: BlockingScraper([]), Backend.BUNDESAGENTUR: BlockingScraper([])}
    )
    outcome = orchestrator.search(_params("indeed", "arbeitsagentur"), cache_dir)

    assert len(outcome.outcomes) == 2
