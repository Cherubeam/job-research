"""Tests for the Gradio entry point in `ui.app`."""

import threading
from pathlib import Path

import pytest

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams
from job_research.orchestrator import Orchestrator
from job_research.sources import Backend, catalog
from job_research.store import JobStore
from ui import app


class RecordingScraper:
    """Fake backend that records the params it was handed.

    ``barrier`` lets a test hold every in-flight request inside ``search_jobs``
    until all of them have arrived, which makes cross-request interference
    deterministic instead of a race the test might win by luck.
    """

    def __init__(
        self,
        listings: list[JobListing] | None = None,
        barrier: threading.Barrier | None = None,
    ) -> None:
        self.seen_params: list[JobSearchParams] = []
        self._listings = listings or []
        self._barrier = barrier

    def search_jobs(
        self,
        params: JobSearchParams,
        cache_dir: Path,
        cache_duration_hours: int = 24,
    ) -> list[JobListing]:
        self.seen_params.append(params)
        if self._barrier is not None:
            self._barrier.wait(timeout=10)
        return list(self._listings)


class FailingScraper:
    def search_jobs(self, params, cache_dir, cache_duration_hours=24):
        raise RuntimeError("board unreachable")


def install(monkeypatch, scraper, backends=(Backend.JOBSPY,)) -> None:
    """Point the app's orchestrator at *scraper* for the given backends."""
    monkeypatch.setattr(app, "_orchestrator", Orchestrator({b: scraper for b in backends}))


@pytest.fixture
def isolated_output(tmp_path, monkeypatch):
    """Point reports, cache, and the job store at a temp directory.

    The store especially: without this the suite would write into the real
    `data/jobs.db` and quietly mark the user's actual jobs as already seen.
    """
    monkeypatch.setattr(app._config.output, "output_directory", tmp_path / "results")
    monkeypatch.setattr(app._config.output, "cache_directory", tmp_path / "cache")
    monkeypatch.setattr(app, "_store", JobStore(tmp_path / "jobs.db"))
    return tmp_path


def _run(**overrides) -> tuple[str, str, str, str | None]:
    """Drive the generator to completion and return its final yield."""
    kwargs = {
        "keywords": "AI Engineer",
        "location": "Berlin",
        "work_type": "Any",
        "seniority": "All levels",
        "salary_min": 50000,
        "salary_max": 200000,
        "output_format": "markdown",
        "interleave_sites": True,
        "selected_sources": ["indeed"],
    }
    kwargs.update(overrides)
    last = None
    for last in app.run_job_research(**kwargs):
        pass
    assert last is not None
    return last


# ------------------------------------------------------------------ validation


def test_rejects_empty_keywords():
    status, _, _, filepath = _run(keywords="   ")
    assert "Keywords cannot be empty" in status
    assert filepath is None


def test_rejects_inverted_salary_range():
    status, _, _, filepath = _run(salary_min=200000, salary_max=50000)
    assert "cannot be greater than" in status
    assert filepath is None


def test_a_source_no_backend_can_reach_is_reported_as_skipped(monkeypatch, isolated_output):
    """StepStone needs the Claude backend; without it, say so rather than return nothing."""
    install(monkeypatch, RecordingScraper([]), backends=(Backend.JOBSPY,))

    status, _, _, _ = _run(selected_sources=["stepstone"])

    assert "No listings returned" in status
    assert "StepStone.de: skipped" in status
    assert "claude" in status


def test_surfaces_scraper_errors(monkeypatch, isolated_output):
    install(monkeypatch, FailingScraper())
    status, _, _, filepath = _run()
    assert "board unreachable" in status
    assert filepath is None


def test_every_selected_source_is_reported(monkeypatch, isolated_output):
    """Sources are named explicitly: reading them from the ambient .env would
    make this test depend on whatever the developer happens to have configured."""
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    install(monkeypatch, scraper, backends=(Backend.JOBSPY, Backend.BUNDESAGENTUR))

    _, _, report, _ = _run(selected_sources=["indeed", "arbeitsagentur"])

    assert "## Sources" in report
    assert "Indeed.de" in report
    assert "Arbeitsagentur.de" in report


def test_an_empty_selection_falls_back_to_the_configured_sources(monkeypatch, isolated_output):
    """An empty checkbox group must not silently mean "search nothing"."""
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    install(monkeypatch, scraper, backends=(Backend.JOBSPY, Backend.BUNDESAGENTUR))
    monkeypatch.setattr(app._config.search_params, "enabled_sources", ["arbeitsagentur"])

    _run(selected_sources=[])

    assert scraper.seen_params[0].enabled_sources == ["arbeitsagentur"]


def test_the_same_job_from_two_sources_is_merged_with_provenance(monkeypatch, isolated_output):
    """The payoff of running sources together: one entry, both links."""
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme", location="Berlin")])
    install(monkeypatch, scraper, backends=(Backend.JOBSPY, Backend.BUNDESAGENTUR))

    _, _, report, _ = _run(selected_sources=["indeed", "arbeitsagentur"])

    assert report.count("### 1. AI Engineer") == 1
    assert "### 2." not in report


# ----------------------------------------------------------------- happy path


def test_writes_report_and_returns_its_path(monkeypatch, isolated_output):
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    install(monkeypatch, scraper)

    status, _, report, filepath = _run()

    assert "**Done**" in status
    assert filepath is not None
    written = Path(filepath)
    assert written.exists()
    assert written.read_text(encoding="utf-8") == report
    assert "AI Engineer" in report


def test_csv_output_is_fenced_for_markdown_rendering(monkeypatch, isolated_output):
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    install(monkeypatch, scraper)

    _, _, report, filepath = _run(output_format="csv")

    assert report.startswith("```\n")
    assert filepath is not None and filepath.endswith(".csv")
    # The fence is presentation only; the saved file stays valid CSV.
    assert not Path(filepath).read_text(encoding="utf-8").startswith("```")


def test_applies_seniority_filter_to_scraper_output(monkeypatch, isolated_output):
    scraper = RecordingScraper(
        [
            JobListing(title="Senior AI Engineer", company="Acme"),
            JobListing(title="Junior AI Engineer", company="Acme"),
        ]
    )
    install(monkeypatch, scraper)

    status, _, report, _ = _run(seniority="Senior")

    assert "Senior AI Engineer" in report
    assert "Junior AI Engineer" not in report
    assert "1 of 2 fetched listings match" in status


def test_reports_truncation_against_the_matched_count(monkeypatch, isolated_output):
    scraper = RecordingScraper(
        [JobListing(title=f"AI Engineer {i}", company="Acme") for i in range(5)]
    )
    install(monkeypatch, scraper)
    monkeypatch.setattr(app._config, "max_jobs_per_search", 2)

    status, _, _, _ = _run()

    assert "Showing 2 of 5 matching listings" in status


# ------------------------------------------------------- concurrency (F4)


def test_concurrent_searches_do_not_share_parameters(monkeypatch, isolated_output):
    """Regression test for F4.

    Both requests are held inside `search_jobs` until each has recorded its
    params. When `run_job_research` mutated the module-level config, the second
    request's keywords overwrote the first's before either was read, and both
    searches ran the same query.
    """
    barrier = threading.Barrier(2)
    scraper = RecordingScraper(barrier=barrier)
    install(monkeypatch, scraper)

    errors: list[BaseException] = []

    def drive(keywords: str) -> None:
        try:
            for _ in app.run_job_research(
                keywords=keywords,
                location="Berlin",
                work_type="Any",
                seniority="All levels",
                salary_min=50000,
                salary_max=200000,
                output_format="markdown",
                interleave_sites=True,
            ):
                pass
        except BaseException as exc:  # pragma: no cover - surfaced via assertion
            errors.append(exc)

    threads = [
        threading.Thread(target=drive, args=("AI Engineer",)),
        threading.Thread(target=drive, args=("Data Scientist",)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert not errors
    assert not any(thread.is_alive() for thread in threads)
    assert {params.keywords for params in scraper.seen_params} == {
        "AI Engineer",
        "Data Scientist",
    }


def test_search_params_carry_defaults_the_ui_does_not_expose(monkeypatch, isolated_output):
    """Fields absent from the form (e.g. title alternatives) keep their config values."""
    scraper = RecordingScraper([JobListing(title="AI Engineer")])
    install(monkeypatch, scraper)

    before = app._config.search_params.keywords
    _run(keywords="Quantum Cartographer")

    params = scraper.seen_params[0]
    assert params.keywords == "Quantum Cartographer"
    assert params.job_title_alternatives == app._config.search_params.job_title_alternatives
    # The module-level config must be untouched by the request. Compare via a
    # bool: asserting on the objects makes pytest repr the whole Config, which
    # puts CLAUDE_API_KEY in the failure output and therefore in CI logs.
    shares_params_object = app._config.search_params is params
    assert not shares_params_object
    assert app._config.search_params.keywords == before


# --------------------------------------------------------- relevance wiring


def test_excluded_keywords_from_the_form_reach_the_pipeline(monkeypatch, isolated_output):
    scraper = RecordingScraper(
        [
            JobListing(title="AI Engineer", company="Acme"),
            JobListing(title="Werkstudent AI Engineer", company="Globex"),
        ]
    )
    install(monkeypatch, scraper)

    _, _, report, _ = _run(excluded_keywords="Werkstudent, Praktikum")

    assert "AI Engineer" in report
    assert "Werkstudent" not in report
    assert scraper.seen_params[0].excluded_keywords == ["Werkstudent", "Praktikum"]


def test_irrelevant_titles_are_filtered_out_of_the_report(monkeypatch, isolated_output):
    scraper = RecordingScraper(
        [
            JobListing(title="AI Engineer", company="Acme"),
            JobListing(title="Shopify Backend Developer", company="Globex"),
        ]
    )
    install(monkeypatch, scraper)

    _, _, report, _ = _run(keywords="AI Engineer")

    assert "AI Engineer" in report
    assert "Shopify" not in report


# ------------------------------------------------------ source selection (F2)


def test_selected_sources_reach_the_scraper(monkeypatch, isolated_output):
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    install(monkeypatch, scraper)

    _run(selected_sources=["indeed"])

    assert scraper.seen_params[0].enabled_sources == ["indeed"]


def test_source_choices_only_offer_what_some_available_backend_can_reach():
    offered = {source_id for _, source_id in app._source_choices()}
    reachable = {s.id for s in catalog.all_sources() if any(s.supports(b) for b in app._scrapers)}
    assert offered == reachable


def test_sources_with_a_caveat_are_flagged_in_their_label():
    labels = {source_id: label for label, source_id in app._source_choices()}
    for source in app._selectable_sources():
        if source.caveat:
            assert labels[source.id].endswith("⚠")


# ------------------------------------------------------- run-over-run (F11)


def test_first_run_marks_every_listing_as_new(monkeypatch, isolated_output):
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    install(monkeypatch, scraper)

    status, _, report, _ = _run()

    assert "1 new since last run" in status
    assert "🆕" in report
    assert "- **New since last run:** 1" in report


def test_a_repeat_search_reports_nothing_new(monkeypatch, isolated_output):
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    install(monkeypatch, scraper)

    _run()
    status, _, report, _ = _run()

    assert "nothing new" in status
    assert "🆕" not in report


def test_only_new_shows_just_the_unseen_listings(monkeypatch, isolated_output):
    first = JobListing(title="AI Engineer", company="Acme")
    install(monkeypatch, RecordingScraper([first]))
    _run()

    second = JobListing(title="ML Engineer", company="Globex")
    install(monkeypatch, RecordingScraper([first, second]))
    status, _, report, _ = _run(only_new=True)

    # Assert on listing headings: the report *title* echoes the keywords, so a
    # bare substring check would match "Job Search Results: AI Engineer".
    assert "### 1. ML Engineer" in report
    assert "### 1. AI Engineer" not in report
    assert "### 2." not in report  # only the new one is listed
    assert "1 new of 2 matching listings" in status


def test_listings_hidden_by_only_new_are_still_recorded(monkeypatch, isolated_output):
    """Otherwise everything filtered out today reappears as new tomorrow."""
    listings = [
        JobListing(title="AI Engineer", company="Acme"),
        JobListing(title="ML Engineer", company="Globex"),
    ]
    install(monkeypatch, RecordingScraper(listings))

    _run(only_new=True)
    status, _, _, _ = _run()

    assert "nothing new" in status
    assert app._store.count() == 2


def test_the_same_job_from_another_source_is_not_new_again(monkeypatch, isolated_output):
    install(
        monkeypatch,
        RecordingScraper([JobListing(title="AI Engineer", company="Acme", location="Berlin")]),
    )
    _run()

    install(
        monkeypatch,
        RecordingScraper(
            [JobListing(title="AI Engineer (m/w/d)", company="Acme", location="Berlin, Germany")]
        ),
    )
    status, _, _, _ = _run()

    assert "nothing new" in status
