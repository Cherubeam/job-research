"""Gradio web interface for job research tool"""

import logging
import os
import threading
import time
from collections.abc import Generator
from dataclasses import replace

import gradio as gr

from job_research import pipeline
from job_research.config import Config, ScraperBackend, SeniorityLevel, WorkType
from job_research.sources import Backend, catalog
from job_research.analyzer import JobAnalyzer
from job_research.jobspy_scraper import JobSpyScraper
from job_research.sources.bundesagentur import BundesagenturScraper
from job_research.store import JobStore
from job_research.orchestrator import JobScraper, Orchestrator
from job_research.scraper import ClaudeScraper
from job_research.utils import generate_output_filename
from ui.log_capture import LogCaptureHandler

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)

_config = Config.from_env()
_store = JobStore(_config.output.store_path)


def _build_scrapers(config: Config) -> dict[Backend, JobScraper]:
    """Every backend that can actually run, given what is configured.

    jobspy and Bundesagentur need no credentials, so they are always available;
    Claude needs an API key and is simply absent without one.
    """
    scrapers: dict[Backend, JobScraper] = {
        Backend.JOBSPY: JobSpyScraper(max_jobs=config.max_jobs_per_search),
        Backend.BUNDESAGENTUR: BundesagenturScraper(max_jobs=config.max_jobs_per_search),
    }
    if config.claude_api_key:
        scrapers[Backend.CLAUDE] = ClaudeScraper(
            api_key=config.claude_api_key,
            model=config.claude_model,
            max_jobs=config.max_jobs_per_search,
        )
    else:
        logger.info("No CLAUDE_API_KEY — the Claude backend is unavailable")
    return scrapers


_PREFERRED_BACKEND = {
    ScraperBackend.JOBSPY: Backend.JOBSPY,
    ScraperBackend.BUNDESAGENTUR: Backend.BUNDESAGENTUR,
    ScraperBackend.CLAUDE: Backend.CLAUDE,
}[_config.scraper_backend]

_scrapers = _build_scrapers(_config)
_orchestrator = Orchestrator(_scrapers, preferred=_PREFERRED_BACKEND)
logger.info(
    "Backends available: %s (preferred: %s)",
    ", ".join(sorted(b.value for b in _scrapers)),
    _PREFERRED_BACKEND.value,
)


def _selectable_sources() -> tuple:
    """Sources some available backend can reach."""
    return tuple(
        source
        for source in catalog.all_sources()
        if any(source.supports(backend) for backend in _scrapers)
    )


def _source_choices() -> list[tuple[str, str]]:
    """Selectable sources as (label, id) pairs, caveated ones flagged."""
    return [
        (f"{source.label} ⚠" if source.caveat else source.label, source.id)
        for source in _selectable_sources()
    ]


def _source_caveats() -> str:
    """Markdown footnotes for sources that carry a caveat."""
    return "\n".join(f"- **{s.label}** — {s.caveat}" for s in _selectable_sources() if s.caveat)


def run_job_research(
    keywords: str,
    location: str,
    work_type: str,
    seniority: str,
    salary_min: int,
    salary_max: int,
    output_format: str,
    interleave_sites: bool = True,
    excluded_keywords: str = "",
    selected_sources: list[str] | None = None,
    posted_within_days: int | None = None,
    only_new: bool = False,
) -> Generator[tuple[str, str, str, str | None], None, None]:
    """Run job research with given parameters. Yields (status_md, log_text, report_md, filepath)."""
    if not keywords.strip():
        yield ("**Error:** Keywords cannot be empty", "", "", None)
        return

    if salary_min > salary_max:
        yield ("**Error:** Minimum salary cannot be greater than maximum", "", "", None)
        return

    # Set up log capture
    handler = LogCaptureHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    root_logger = logging.getLogger("job_research")
    root_logger.addHandler(handler)

    # Per-request params. Never mutate the module-level config: two concurrent
    # searches would otherwise overwrite each other's parameters mid-flight.
    params = replace(
        _config.search_params,
        keywords=keywords,
        location=location,
        work_type=WorkType(work_type),
        seniority_level=SeniorityLevel(seniority),
        salary_minimum=salary_min,
        salary_maximum=salary_max,
        excluded_keywords=[k.strip() for k in excluded_keywords.split(",") if k.strip()],
        posted_within_days=posted_within_days or None,
        enabled_sources=(
            list(selected_sources)
            if selected_sources
            else list(_config.search_params.enabled_sources)
        ),
    )

    # Run search in background thread
    result_holder: dict = {}

    def _search() -> None:
        try:
            result_holder["outcome"] = _orchestrator.search(
                params=params,
                cache_dir=_config.output.cache_directory,
                cache_duration_hours=_config.output.cache_duration_hours,
            )
        except Exception as exc:
            result_holder["error"] = exc

    thread = threading.Thread(target=_search, daemon=True)
    thread.start()

    try:
        # Poll and yield updates while search is running
        while thread.is_alive():
            latest = handler.get_latest()
            status_detail = f" — {latest}" if latest else ""
            yield (
                f"**Searching...**{status_detail}",
                handler.get_all(),
                "",
                None,
            )
            time.sleep(0.5)

        # Thread finished — check result
        if "error" in result_holder:
            yield (
                f"**Error:** {result_holder['error']}",
                handler.get_all(),
                "",
                None,
            )
            return

        outcome = result_holder["outcome"]
        source_report = outcome.summary()

        if not outcome.listings:
            # Every source came back empty, failed, or was unreachable. Say which,
            # rather than letting a broken source look like a quiet job market.
            yield (
                "**Error:** No listings returned.\n\n" + source_report,
                handler.get_all(),
                "",
                None,
            )
            return

        result = pipeline.apply(
            outcome.listings,
            params,
            max_jobs=_config.max_jobs_per_search,
            interleave=interleave_sites,
        )
        # Record before filtering to "new only": a listing you never display is
        # still one you have now seen, and marking it otherwise would make it
        # reappear as new on the next run.
        diff = _store.record(result.listings)
        new_ids = {lst.job_id for lst in diff.new}

        shown_listings = diff.new if only_new else result.listings
        analyzer = JobAnalyzer(
            new_ids=new_ids,
            source_notes=[o.describe() for o in outcome.outcomes],
        )
        analyzer.add_listings(shown_listings)

        ext = "csv" if output_format == "csv" else "md"
        if output_format == "markdown":
            report = analyzer.generate_markdown_report(f"Job Search Results: {keywords}")
        else:
            report = analyzer.generate_csv_report()

        # Save report to file
        output_dir = _config.output.output_directory
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = generate_output_filename("job_search", ext)
        filepath = output_dir / filename
        filepath.write_text(report, encoding="utf-8")
        logger.info("Report saved to %s", filepath)

        shown = len(shown_listings)
        new_note = f" — {len(diff.new)} new since last run" if diff.new else " — nothing new"
        if only_new:
            status = (
                f"**Done** — {len(diff.new)} new of {result.matched} matching listings. "
                f"Saved to `{filename}`"
            )
        elif result.truncated:
            status = (
                f"**Done** — Showing {shown} of {result.matched} matching listings "
                f"(from {result.fetched} fetched). "
                f"Increase `MAX_JOBS_PER_SEARCH` for more.{new_note}. Saved to `{filename}`"
            )
        elif result.matched < result.fetched:
            status = (
                f"**Done** — {shown} of {result.fetched} fetched listings match "
                f"your filters{new_note}. Saved to `{filename}`"
            )
        else:
            status = f"**Done** — Found {shown} listings{new_note}. Saved to `{filename}`"

        # Wrap CSV in a code fence so it renders in Markdown
        if output_format == "csv":
            report_md = f"```\n{report}\n```"
        else:
            report_md = report

        if outcome.failed:
            status += (
                f"\n\n**{len(outcome.failed)} source(s) failed** — results are "
                "incomplete:\n\n" + "\n".join(f"- {o.describe()}" for o in outcome.failed)
            )

        yield (status, handler.get_all(), report_md, str(filepath))

    except Exception as e:
        logger.exception("run_job_research failed")
        yield (f"**Error:** {e}", handler.get_all(), "", None)

    finally:
        root_logger.removeHandler(handler)


def create_ui() -> gr.Blocks:
    """Create and configure the Gradio interface"""

    demo: gr.Blocks
    with gr.Blocks(title="Job Research Tool", theme=gr.themes.Soft()) as demo:
        gr.Markdown(
            """
        # Job Market Research Tool

        Search for AI/ML jobs across German job boards with customizable filters.
        """
        )

        with gr.Tabs():
            with gr.Tab("Search"):
                with gr.Row():
                    with gr.Column(scale=1):
                        gr.Markdown("### Search Parameters")

                        keywords = gr.Textbox(
                            label="Job Keywords",
                            value="AI Engineer",
                            placeholder="e.g., 'AI Engineer', 'Machine Learning'",
                        )

                        location = gr.Textbox(
                            label="Location",
                            value="All of Germany",
                            placeholder="e.g., 'Berlin', 'Munich' or 'All of Germany'",
                        )

                    with gr.Column(scale=1):
                        gr.Markdown("### Further Filters")
                        work_type = gr.Dropdown(
                            label="Work Type",
                            choices=[wt.value for wt in WorkType],
                            value=WorkType.HYBRID.value,
                        )

                        seniority = gr.Dropdown(
                            label="Seniority Level",
                            choices=[sl.value for sl in SeniorityLevel],
                            value=SeniorityLevel.ALL.value,
                        )

                with gr.Row():
                    with gr.Column(scale=1):
                        salary_min = gr.Number(
                            label="Minimum Salary (EUR)",
                            value=50000,
                            precision=0,
                        )

                    with gr.Column(scale=1):
                        salary_max = gr.Number(
                            label="Maximum Salary (EUR)",
                            value=200000,
                            precision=0,
                        )

                with gr.Row():
                    output_format = gr.Radio(
                        label="Output Format",
                        choices=["markdown", "csv"],
                        value="markdown",
                    )

                    posted_within = gr.Number(
                        label="Posted within (days)",
                        value=_config.search_params.posted_within_days,
                        precision=0,
                        minimum=0,
                        info="Leave empty for no limit. Listings with no date are kept.",
                    )

                    source_input = gr.CheckboxGroup(
                        label="Job Sources",
                        choices=_source_choices(),
                        value=[
                            s
                            for s in _config.search_params.enabled_sources
                            if s in {sid for _, sid in _source_choices()}
                        ],
                        info="All selected sources are searched in one run.",
                    )

                    exclude_input = gr.Textbox(
                        label="Exclude titles containing",
                        placeholder="e.g. Werkstudent, Praktikum, Sales",
                        info="Comma-separated. Matched on whole words.",
                        value=", ".join(_config.search_params.excluded_keywords),
                    )

                if _source_caveats():
                    gr.Markdown(_source_caveats())

                with gr.Row():
                    only_new = gr.Checkbox(
                        label="Only listings new since the last run",
                        value=False,
                    )

                    interleave_sites = gr.Checkbox(
                        label="Interleave results from different job boards",
                        value=_config.interleave_sites,
                    )

                search_btn = gr.Button("Search Jobs", variant="primary", size="lg")

                status_output = gr.Markdown(value="")

                with gr.Accordion("Search Log", open=False):
                    log_output = gr.Code(language=None, lines=12)

                results_output = gr.Markdown(value="")

                download_file = gr.File(label="Download Results")

            with gr.Tab("Info"):
                gr.Markdown(
                    """
                ## About This Tool

                Searches German job boards for AI/ML roles. **Every selected
                source is searched in one run**, each through whichever backend
                can reach it, and the results are merged and deduplicated.

                ### Backends
                - **jobspy** — Indeed (and LinkedIn, if enabled). No API key.
                - **bundesagentur** — the federal job board's own API. No API key.
                  The largest German corpus, and the only source with structured
                  salary. Unofficial endpoint — see `docs/decisions/001-...`.
                - **claude** — Anthropic web search, restricted per source.
                  Reaches boards the other two cannot (StepStone, Monster,
                  Honeypot, startup.jobs). Requires `CLAUDE_API_KEY` and costs
                  money per search, so it is used only where nothing free can
                  reach the source.

                `SCRAPER_BACKEND` sets a *preference*: it wins wherever it can
                serve a source, and the rest fall back to whatever can.

                Each run reports what every source returned, so a source that
                failed is visible rather than looking like a quiet job market.

                ### How filters are applied
                - **Location** and **work type** are passed to the backend and
                  shape what gets fetched.
                - **Relevance** scores each title against your keywords and the
                  configured alternatives, keeping those that cover more than
                  half of any one phrase. "Sales Engineer" covers 1 of the 2
                  tokens in "AI Engineer", so it is dropped.
                - **Exclude titles containing** drops matching titles outright,
                  matched on whole words — excluding "sales" will not reject
                  "Salesforce Engineer".
                - **Salary** is applied locally, by overlap. Listings that state
                  no salary are kept — most German postings omit it, and dropping
                  them would discard the majority of real results.
                - **Seniority** is applied locally and inferred from the job
                  title (for example "Senior", "Junior", "Werkstudent",
                  "Teamleiter"). Job boards expose no reliable seniority field, so
                  this is a heuristic.

                Hourly and monthly pay is converted to an annual figure before
                comparison (40h x 52 weeks for hourly), so salary filtering and
                statistics compare like with like. Figures that cannot be pay for
                the stated period — contract hours, a posting year — are ignored.

                Because salary and seniority are applied after the fetch, changing
                them re-filters the cached results instead of re-running the search.

                ### What's new
                Every posting seen is recorded locally, so each run marks which
                listings are 🆕 since last time — and "Only listings new since the
                last run" narrows the report to those. Postings found on several
                boards are merged into one entry that keeps every link.

                ### Caching
                Fetches are cached for 24h, keyed only on what the backend
                actually received. The cached set is the full unfiltered fetch.

                ### Tips
                1. Start broad, then narrow with salary and seniority — those are
                   free to adjust once a search has been cached.
                2. Export to CSV for further analysis in Excel or Sheets.
                3. Raise `MAX_JOBS_PER_SEARCH` if the status line reports that
                   results were truncated.
                """
                )

        search_btn.click(
            fn=run_job_research,
            inputs=[
                keywords,
                location,
                work_type,
                seniority,
                salary_min,
                salary_max,
                output_format,
                interleave_sites,
                exclude_input,
                source_input,
                posted_within,
                only_new,
            ],
            outputs=[status_output, log_output, results_output, download_file],
        )

    return demo


def main() -> None:
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))
    demo = create_ui()
    demo.launch(
        server_name="127.0.0.1",
        server_port=port,
        share=False,
        show_error=True,
        inbrowser=True,
    )


if __name__ == "__main__":
    main()
