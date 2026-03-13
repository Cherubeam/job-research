# Job Research Tool

A Python-based job market research tool with a Gradio UI for searching and analyzing AI/ML job listings across German job boards. Uses the **Anthropic Claude API** (`web_search_20250305` tool) for all web searching — no direct scraping, no blocking risk.

## Features

- **Claude-Powered Search**: Delegates job searching to Anthropic's infrastructure via the `web_search_20250305` tool
- **Multi-board Coverage**: StepStone, LinkedIn, Indeed, XING, Honeypot, and more
- **Flexible Filters**: Filter by location, salary range, seniority level, and work type
- **Data Analysis**: Automatic salary analysis, job distribution, and market insights
- **Multiple Export Formats**: Generate reports in Markdown or CSV
- **Smart Caching**: 24h cache reduces API calls for repeated searches
- **Web Interface**: User-friendly Gradio UI

## Quick Start

### Prerequisites

- Python 3.13+
- `uv` package manager
- Anthropic API key (for scraping)

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

1. **Search Tab**: Enter keywords, location, work type, seniority, salary range
2. **Click "Search Jobs"** — results via Claude web search (~10-30s first time, <1s cached)
3. **Results Tab**: View report, export to CSV or Markdown

### Configuration

Edit `.env`:
```bash
# Required
CLAUDE_API_KEY=sk-ant-...

# Optional
CLAUDE_MODEL=claude-opus-4-6
MAX_JOBS_PER_SEARCH=20
JOB_KEYWORDS=AI Engineer
LOCATION=All of Germany
WORK_TYPE=Remote/Hybrid
SALARY_MINIMUM=50000
SALARY_MAXIMUM=200000
```

## Project Structure

```
job-research/
├── src/
│   ├── job_research/
│   │   ├── __init__.py
│   │   ├── config.py       # Configuration management
│   │   ├── scraper.py      # Claude API web search scraper
│   │   ├── analyzer.py     # Job analysis and reporting
│   │   └── utils.py        # Caching, formatting, parsing
│   └── ui/
│       └── app.py          # Gradio application + main()
├── docs/
│   ├── setup.md            # Detailed setup guide
│   ├── project-structure.md
│   └── scraper-design.md
├── tests/                  # pytest test suite
├── data/
│   ├── results/            # Output reports
│   └── cache/              # Cached search results
├── pyproject.toml
└── .env.example
```

## Dependencies

- **anthropic** (0.49+) — Claude API with web search tool
- **gradio** (4.0+) — Web interface
- **python-dotenv** (1.0+) — Environment configuration
- **pandas** (2.0+) — Data analysis

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

## License

MIT License

---

**Version:** 0.1.0
