"""Tests for the Gradio entry point in `ui.app`."""

import threading
from pathlib import Path

import pytest

from job_research.analyzer import JobListing
from job_research.config import JobSearchParams
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


@pytest.fixture
def isolated_output(tmp_path, monkeypatch):
    """Point report and cache output at a temp directory."""
    monkeypatch.setattr(app._config.output, "output_directory", tmp_path / "results")
    monkeypatch.setattr(app._config.output, "cache_directory", tmp_path / "cache")
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


def test_reports_missing_scraper(monkeypatch):
    monkeypatch.setattr(app, "_scraper", None)
    status, _, report, _ = _run()
    assert "Scraper not initialized" in status
    assert "SCRAPER_BACKEND" in report


def test_surfaces_scraper_errors(monkeypatch, isolated_output):
    monkeypatch.setattr(app, "_scraper", FailingScraper())
    status, _, _, filepath = _run()
    assert "board unreachable" in status
    assert filepath is None


# ----------------------------------------------------------------- happy path


def test_writes_report_and_returns_its_path(monkeypatch, isolated_output):
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    monkeypatch.setattr(app, "_scraper", scraper)

    status, _, report, filepath = _run()

    assert "**Done**" in status
    assert filepath is not None
    written = Path(filepath)
    assert written.exists()
    assert written.read_text(encoding="utf-8") == report
    assert "AI Engineer" in report


def test_csv_output_is_fenced_for_markdown_rendering(monkeypatch, isolated_output):
    scraper = RecordingScraper([JobListing(title="AI Engineer", company="Acme")])
    monkeypatch.setattr(app, "_scraper", scraper)

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
    monkeypatch.setattr(app, "_scraper", scraper)

    status, _, report, _ = _run(seniority="Senior")

    assert "Senior AI Engineer" in report
    assert "Junior AI Engineer" not in report
    assert "1 of 2 fetched listings match" in status


def test_reports_truncation_against_the_matched_count(monkeypatch, isolated_output):
    scraper = RecordingScraper(
        [JobListing(title=f"AI Engineer {i}", company="Acme") for i in range(5)]
    )
    monkeypatch.setattr(app, "_scraper", scraper)
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
    monkeypatch.setattr(app, "_scraper", scraper)

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
    monkeypatch.setattr(app, "_scraper", scraper)

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
