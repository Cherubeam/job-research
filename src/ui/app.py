"""Gradio web interface for job research tool"""

import logging
import os

import gradio as gr

from job_research.config import Config, SeniorityLevel, WorkType, OutputFormat
from job_research.analyzer import JobAnalyzer
from job_research.scraper import ClaudeScraper
from job_research.utils import generate_output_filename

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)

_config = Config.from_env()
_scraper: ClaudeScraper | None = None
try:
    if _config.claude_api_key:
        _scraper = ClaudeScraper(
            api_key=_config.claude_api_key,
            model=_config.claude_model,
            max_jobs=_config.max_jobs_per_search,
            board_config=_config.job_boards,
        )
except Exception:
    logger.exception("Failed to initialize ClaudeScraper")


def run_job_research(
    keywords: str,
    location: str,
    work_type: str,
    seniority: str,
    salary_min: int,
    salary_max: int,
    output_format: str,
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
                "CLAUDE_API_KEY is not set.\n\n"
                "To fix:\n"
                "1. Copy .env.example to .env\n"
                "2. Set CLAUDE_API_KEY=your-key\n"
                "3. Restart the app",
                None,
            )

        config = Config()
        config.search_params.keywords = keywords
        config.search_params.location = location
        config.search_params.work_type = WorkType(work_type)
        config.search_params.seniority_level = SeniorityLevel(seniority)
        config.search_params.salary_minimum = salary_min
        config.search_params.salary_maximum = salary_max
        config.output.output_format = OutputFormat(output_format)

        listings = _scraper.search_jobs(
            config.search_params,
            config.output.cache_directory,
            config.output.cache_duration_hours,
        )

        if not listings:
            return (
                "No results found",
                "No job listings found for the given search parameters.\n\n"
                "Try broadening your search (e.g., different keywords or location).",
                None,
            )

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

        status = f"Search completed! Found {analyzer.get_total_count()} listings. Saved to {filename}"
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
            inputs=[keywords, location, work_type, seniority, salary_min, salary_max, output_format],
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
