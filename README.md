![Python 3.13+](https://img.shields.io/badge/python-3.13%2B-blue)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Version 0.3.0](https://img.shields.io/badge/version-0.3.0-orange)

# Job Research Tool

AI-powered job market research tool for searching and analyzing job listings across German job boards.

## Overview

Job Research Tool aggregates job listings from major German job boards through two independent scraper backends — one powered by Anthropic's Claude API with web search, the other by the python-jobspy library. A quality pipeline handles relevance filtering, deduplication, and salary normalization before results are analyzed and displayed in an interactive Gradio web UI. Searches are cached for 24 hours to minimize API costs on repeated queries.

## Features

- **Dual Scraper Backends**: Claude API web search (`web_search_20250305`) and python-jobspy for broad coverage
- **Job Board Support**: Indeed.de, LinkedIn, and other German job boards — selectable per search
- **Quality Pipeline**: Relevance scoring, cross-source deduplication, and salary normalization
- **Multi-Source Interleaving**: Results from different boards are round-robin mixed for balanced representation
- **Flexible Filters**: Location, salary range, seniority level, and work type
- **Data Analysis**: Automatic salary analysis, job distribution, and market insights
- **Multiple Export Formats**: Reports in Markdown or CSV
- **Smart Caching**: 24h cache reduces API calls for repeated searches
- **Web Interface**: User-friendly Gradio UI

## Quick Start

### Prerequisites

- Python 3.13+
- `uv` package manager
- Anthropic API key (for Claude-powered scraping)

### Installation

1. **Install `uv`** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env — set CLAUDE_API_KEY at minimum
   ```

### Running the Application

```bash
uv run python src/ui/app.py
# or:
uv run job-research
```

Opens at **http://127.0.0.1:7860**

## Usage

### Web Interface

1. Enter keywords, location, work type, seniority, and salary range
2. **Click "Search Jobs"** — a live status line and expandable log panel show progress
3. Results render inline as formatted Markdown (or CSV in a code block) with a download link

### Configuration

Edit `.env`:
```bash
# Required
CLAUDE_API_KEY=sk-ant-...

# Optional
CLAUDE_MODEL=claude-haiku-4-5-20251001
MAX_JOBS_PER_SEARCH=200        # max results to show (default 200)
INTERLEAVE_SITES=true          # mix results from different job boards
JOB_KEYWORDS=AI Engineer
LOCATION=All of Germany
WORK_TYPE=Remote/Hybrid
SALARY_MINIMUM=50000
SALARY_MAXIMUM=200000
```

## Architecture

The tool uses a **dual-backend design** to maximize coverage and reliability:

- **ClaudeScraper** — delegates search to Anthropic's `web_search_20250305` tool. Claude interprets the query, searches the web, and extracts structured job data. High accuracy, API cost per search.
- **JobSpyScraper** — uses the python-jobspy library to query Indeed, LinkedIn, and other boards directly. Fast and free, but relies on site structure stability.

Both backends produce a common `JobListing` data model (Pydantic). Results pass through a **quality pipeline**:

1. **Relevance filtering** — scores each listing against the original query and drops low-relevance noise
2. **Deduplication** — identifies duplicate listings across sources using title/company/location similarity
3. **Salary normalization** — standardizes salary formats (annual, monthly, hourly) to comparable ranges

The `JobAnalyzer` then generates summary statistics and a formatted report for the UI.

```
Gradio UI → run_job_research()
               ├── ClaudeScraper.search_jobs()   ─┐
               └── JobSpyScraper.search_jobs()    ─┤
                                                   ▼
                                        Quality Pipeline
                                        (filter → dedup → normalize)
                                                   ▼
                                            JobAnalyzer → Report
```

## Project Structure

```
job-research/
├── src/
│   ├── job_research/
│   │   ├── __init__.py
│   │   ├── config.py           # Configuration management
│   │   ├── scraper.py          # ClaudeScraper (Claude API web search)
│   │   ├── jobspy_scraper.py   # JobSpyScraper (python-jobspy)
│   │   ├── boards.py           # Job board definitions and site config
│   │   ├── analyzer.py         # Job analysis and reporting
│   │   └── utils.py            # Caching, formatting, parsing
│   └── ui/
│       └── app.py              # Gradio application + main()
├── docs/
│   ├── setup.md                # Detailed setup guide
│   ├── project-structure.md    # File-by-file breakdown
│   ├── scraper-design.md       # Scraper architecture decisions
│   └── changelog.md            # Version history
├── tests/                      # pytest test suite
├── data/
│   ├── results/                # Output reports
│   └── cache/                  # Cached search results
├── pyproject.toml
└── .env.example
```

## Dependencies

- **anthropic** (0.49+) — Claude API with web search tool
- **python-jobspy** (1.1+) — Direct job board scraping
- **pydantic** (2.0+) — Data validation and job listing models
- **gradio** (4.0+) — Web interface
- **pandas** (2.0+) — Data analysis
- **python-dotenv** (1.0+) — Environment configuration

## Development

```bash
# Run tests
uv run pytest tests/ -v

# Code quality
uv run black src/
uv run ruff check src/ tests/
uv run mypy src/
```

## Docs

- [Setup Guide](docs/setup.md)
- [Project Structure](docs/project-structure.md)
- [Scraper Design](docs/scraper-design.md)
- [Changelog](docs/changelog.md)

## License

MIT License

---

**Version:** 0.3.0
