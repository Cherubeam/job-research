[![CI](https://github.com/Cherubeam/job-research/actions/workflows/ci.yml/badge.svg)](https://github.com/Cherubeam/job-research/actions/workflows/ci.yml)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
![Version 0.3.0](https://img.shields.io/badge/version-0.3.0-green.svg)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

# Job Research Tool

AI-powered job market research tool for searching and analyzing job listings across German job boards.

## Overview

Job Research Tool aggregates job listings from German job boards through two independent scraper backends — one powered by Anthropic's Claude API with web search, the other by the python-jobspy library. Results pass through a shared post-fetch pipeline (salary and seniority filtering, board interleaving, truncation) before being analyzed and displayed in an interactive Gradio web UI. Fetches are cached for 24 hours to minimize API costs on repeated queries.

## Features

- **Dual Scraper Backends**: Claude API web search (`web_search_20250305`) and python-jobspy — one selected per run via `SCRAPER_BACKEND`
- **Source Registry**: One place declares every board, which backends can reach it, and how to recognise its listing URLs. The UI offers only sources the active backend can actually search
- **Relevance Scoring**: Titles are scored against your keywords and alternatives, with a configurable threshold and a negative-keyword list
- **Post-Fetch Filters**: Salary by range overlap, seniority inferred from the job title
- **Salary Normalization**: Hourly and monthly pay annualised so filters and statistics compare like with like
- **Multi-Source Interleaving**: Results from different boards are round-robin mixed before truncation, so one board cannot crowd out the rest
- **Cross-Source Deduplication**: One rule for every backend — normalized URL, then title + company + location
- **Data Analysis**: Salary statistics and distribution by board, location, and work type
- **Multiple Export Formats**: Reports in Markdown or CSV
- **Smart Caching**: 24h cache keyed only on what the backend actually received, so adjusting salary or seniority re-filters instead of re-fetching
- **Web Interface**: Gradio UI with live progress and a search log

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
ENABLED_SOURCES=indeed         # which boards to search
EXCLUDED_KEYWORDS=             # drop titles containing these (comma-separated)
RELEVANCE_THRESHOLD=0.6        # phrase coverage a title must reach to be kept
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

Both backends produce a common `JobListing` data model (Pydantic) and return the
**full deduplicated fetch**, which is what gets cached. Everything that shapes the
*view* happens afterwards in `pipeline.py`, so it applies to every backend and can
change without invalidating the cache:

1. **Relevance** — scores each title against the search phrase and its alternatives, keeping those that cover more than half of any one phrase. Negative keywords drop titles outright.
2. **Deduplicate** — collapses the same posting reached through several sources: normalized URL first, then title + company + location.
3. **Salary filter** — keeps listings whose stated range overlaps the requested window. Listings with no stated salary are kept.
4. **Seniority filter** — infers a level from the job title and keeps matching listings. Heuristic; no board exposes a reliable seniority field.
5. **Interleave** — round-robins across boards so truncation does not favour whichever board was scraped first.
6. **Truncate** — cuts to `MAX_JOBS_PER_SEARCH`, last, so filtering never returns fewer results than requested for no reason.

The `JobAnalyzer` then generates summary statistics and a formatted report for the UI.

```
Gradio UI → run_job_research()
               ├── ClaudeScraper.search_jobs()  ─┐   (cached: full fetch)
               └── JobSpyScraper.search_jobs()  ─┤
                                                 ▼
                                          pipeline.apply()
              (relevance → dedup → salary → seniority → interleave → truncate)
                                                 ▼
                                         JobAnalyzer → Report
```

### Sources

| Source | Claude backend | jobspy backend | Default |
|---|---|---|---|
| Indeed.de | yes | yes | on |
| LinkedIn | yes | yes | off — see [ADR-002](docs/decisions/002-linkedin-scraping.md) |
| StepStone.de | yes | — | off |
| Monster.de | yes | — | off |
| Honeypot.io | yes | — | off |
| startup.jobs | yes | — | off |
| Arbeitsagentur.de | yes | — | off — see [ADR-001](docs/decisions/001-bundesagentur-terms-of-use.md) |

Selecting a source the active backend cannot reach searches less rather than
failing; selecting nothing it can reach fails loudly.

Remaining gaps are tracked in the [architecture review](docs/architecture-review.md):
there is no run-over-run persistence yet (F11).

## Project Structure

```
job-research/
├── src/
│   ├── job_research/
│   │   ├── __init__.py
│   │   ├── config.py           # Configuration management
│   │   ├── scraper.py          # ClaudeScraper (Claude API web search)
│   │   ├── jobspy_scraper.py   # JobSpyScraper (python-jobspy)
│   │   ├── sources/            # Source registry (what exists, who can reach it)
│   │   ├── pipeline/           # Relevance, dedup, filters, interleaving
│   │   ├── salary.py           # Salary parsing and annualisation
│   │   ├── analyzer.py         # Job analysis and reporting
│   │   └── utils.py            # Caching, formatting, parsing
│   └── ui/
│       └── app.py              # Gradio application + main()
├── docs/
│   ├── architecture-review.md  # Findings and phased refactor plan
│   ├── decisions/              # Architecture decision records
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
uv run black src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
```

All four gates run in CI on every push and pull request
([.github/workflows/ci.yml](.github/workflows/ci.yml)); they must pass before a
branch merges. To keep `git blame` readable across the bulk reformatting commit:

```bash
git config blame.ignoreRevsFile .git-blame-ignore-revs
```

`tests/test_characterization.py` pins current behaviour — including behaviour
already identified as wrong in the
[architecture review](docs/architecture-review.md). A failing
`test_characterizes_*` test usually means a planned fix landed; update the test
to assert the new behaviour rather than working around it.

## Docs

- [Architecture Review & Refactor Plan](docs/architecture-review.md)
- [Decision Records](docs/decisions/)
- [Setup Guide](docs/setup.md)
- [Project Structure](docs/project-structure.md)
- [Scraper Design](docs/scraper-design.md)
- [Changelog](docs/changelog.md)

## License

MIT License

---

**Version:** 0.3.0
