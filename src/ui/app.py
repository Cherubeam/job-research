"""Gradio web interface for job research tool"""

import logging
import os

import gradio as gr

from job_research.config import Config, OutputFormat, ScraperBackend, SeniorityLevel, WorkType
from job_research.analyzer import JobAnalyzer
from job_research.jobspy_scraper import JobSpyScraper
from job_research.scraper import ClaudeScraper, JobScraper
from job_research.utils import generate_output_filename

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)

_config = Config.from_env()
_scraper: JobScraper | None = None
try:
    if _config.scraper_backend == ScraperBackend.JOBSPY:
        _scraper = JobSpyScraper(max_jobs=_config.max_jobs_per_search)
        logger.info("Using JobSpyScraper (no API key needed)")
    elif _config.claude_api_key:
        _scraper = ClaudeScraper(
            api_key=_config.claude_api_key,
            model=_config.claude_model,
            max_jobs=_config.max_jobs_per_search,
            board_config=_config.job_boards,
        )
        logger.info("Using ClaudeScraper")
except Exception:
    logger.exception("Failed to initialize scraper")


def run_job_research(
    keywords: str,
    location: str,
    work_type: str,
    seniority: str,
    salary_min: int,
    salary_max: int,
    output_format: str,
    interleave_sites: bool = True,
) -> tuple[str, str, str | None]:
    """Run job research with given parameters. Returns (status, report, filepath)."""
    try:
        if not keywords.strip():
            return ("Error", "Keywords cannot be empty", None)

        if salary_min > salary_max:
            return ("Error", "Minimum salary cannot be greater than maximum", None)

        if _scraper is None:
            return (
                "Error: Scraper not initialized",
                "No scraper backend is configured.\n\n"
                "To fix, set SCRAPER_BACKEND in your .env file:\n"
                "- SCRAPER_BACKEND=jobspy          (no API key needed)\n"
                "- SCRAPER_BACKEND=claude          (requires CLAUDE_API_KEY)\n\n"
                "For Claude backend, also set CLAUDE_API_KEY=your-key",
                None,
            )

        _config.search_params.keywords = keywords
        _config.search_params.location = location
        _config.search_params.work_type = WorkType(work_type)
        _config.search_params.seniority_level = SeniorityLevel(seniority)
        _config.search_params.salary_minimum = salary_min
        _config.search_params.salary_maximum = salary_max
        _config.output.output_format = OutputFormat(output_format)

        search_kwargs: dict = {
            "params": _config.search_params,
            "cache_dir": _config.output.cache_directory,
            "cache_duration_hours": _config.output.cache_duration_hours,
        }
        if hasattr(_scraper, "_interleave_by_site"):
            search_kwargs["interleave"] = interleave_sites

        listings = _scraper.search_jobs(**search_kwargs)

        analyzer = JobAnalyzer()
        analyzer.add_listings(listings)

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

        total = getattr(_scraper, "total_found", len(listings))
        if total > len(listings):
            status = (
                f"Search completed! Showing {len(listings)} of {total} found listings. "
                f"Increase MAX_JOBS_PER_SEARCH for more. Saved to {filename}"
            )
        else:
            status = f"Search completed! Found {len(listings)} listings. Saved to {filename}"
        return (status, report, str(filepath))

    except Exception as e:
        logger.exception("run_job_research failed")
        return (f"Error: {str(e)}", "", None)


def create_ui() -> gr.Blocks:
    """Create and configure the Gradio interface"""

    with gr.Blocks(title="Job Research Tool", theme=gr.themes.Soft()) as demo:
        gr.Markdown("""
        # Job Market Research Tool

        Search for AI/ML jobs across German job boards with customizable filters.
        """)

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

                    interleave_sites = gr.Checkbox(
                        label="Interleave results from different job boards",
                        value=_config.interleave_sites,
                    )

                search_btn = gr.Button("Search Jobs", variant="primary", size="lg")

                status_output = gr.Textbox(
                    label="Status",
                    interactive=False,
                    lines=1,
                )

            with gr.Tab("Results"):
                results_output = gr.Textbox(
                    label="Search Results",
                    interactive=False,
                    lines=20,
                    max_lines=50,
                    elem_classes="results-box",
                )

                download_file = gr.File(
                    label="Download Results",
                    visible=False,
                )

            with gr.Tab("Info"):
                gr.Markdown("""
                ## About This Tool

                This tool searches for AI/ML jobs across major German job boards using the
                **Anthropic Claude API** with the `web_search_20250305` tool.

                ### Setup Required
                Set `CLAUDE_API_KEY` in your `.env` file before searching.

                ### Features
                - Search across multiple job boards (StepStone, LinkedIn, Indeed, XING, etc.)
                - Filter by location, salary, seniority, and work type
                - Generate reports in Markdown or CSV format
                - Download results as files for offline use
                - Salary analysis and market insights
                - Smart caching (24h) to reduce API costs

                ### Job Boards Searched
                - StepStone.de
                - Indeed.de
                - LinkedIn
                - XING
                - Monster.de
                - Honeypot.io
                - Startup.jobs
                - Arbeitsagentur.de

                ### Tips
                1. Use broad keywords first to see the market landscape
                2. Filter by location and work type to narrow down results
                3. Export results to CSV for further analysis in Excel/Sheets
                4. Repeated searches with the same parameters use cached results
                """)

        search_btn.click(
            fn=run_job_research,
            inputs=[keywords, location, work_type, seniority, salary_min, salary_max, output_format, interleave_sites],
            outputs=[status_output, results_output, download_file],
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
