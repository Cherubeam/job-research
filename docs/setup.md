# Quick Setup Guide

## One-Time Setup

### 1. Install `uv` Package Manager

If you don't have `uv` installed yet:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Or for Windows:
```powershell
irm https://astral.sh/uv/install.ps1 | iex
```

### 2. Navigate to Project Directory

```bash
cd job-research
```

### 3. Install Dependencies

```bash
uv sync
```

This will:
- Create a Python virtual environment
- Install all dependencies from `pyproject.toml` (including dev tools)
- Install the project in editable mode (makes `job_research` and `ui` importable)

### 4. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` and set the key for whichever LLM provider you want:
`OPENROUTER_API_KEY` (the default, `LLM_PROVIDER=openrouter`) or
`CLAUDE_API_KEY` (`LLM_PROVIDER=anthropic`). Then customize search defaults.

Neither is strictly required — the jobspy and bundesagentur backends need no
key. Without a provider key the LLM backend is simply unavailable, and the
boards only it can reach (StepStone, Monster, Honeypot, startup.jobs) are
reported as skipped.

## Running the Application

### Start the Gradio UI

```bash
uv run python src/ui/app.py
```

The application will be available at: **http://127.0.0.1:7860**

### Or use the installed entry point

```bash
uv run job-research
```

### Alternative: Using python directly

If `uv run` doesn't work, try:

```bash
source .venv/bin/activate
python src/ui/app.py
```

## Project Structure Overview

```
job-research/
├── src/
│   ├── job_research/        # Core job research module
│   │   ├── config.py        # Configuration management
│   │   ├── analyzer.py      # Job data analysis
│   │   ├── providers.py     # OpenRouter / Anthropic web-search providers
│   │   ├── scraper.py       # LLM web search scraper
│   │   └── utils.py         # Utility functions
│   └── ui/
│       └── app.py           # Gradio web interface
├── data/
│   ├── results/             # Output reports go here
│   └── cache/               # Cached search results
├── docs/                    # Documentation
├── tests/                   # Test suite
├── pyproject.toml           # Dependencies and project config
└── .env.example             # Configuration template
```

## Useful Commands

### Running Code Quality Checks

```bash
uv run black src/
uv run ruff check src/
uv run mypy src/
```

### Running Tests

```bash
uv run pytest tests/
```

### Installing Additional Packages

```bash
uv add package-name
```

## Troubleshooting

### Issue: "uv: command not found"

**Solution:** Ensure `uv` is in your PATH:
```bash
~/.local/bin/uv --version
```

Or reinstall:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Issue: "Port 7860 already in use"

```bash
GRADIO_SERVER_PORT=7861 uv run python src/ui/app.py
```

### Issue: Python version error

**Solution:** Ensure you have Python 3.13 or higher:
```bash
uv python install 3.13
```

### Issue: "ModuleNotFoundError: No module named 'job_research'"

**Solution:** Re-run `uv sync` from the project root:
```bash
uv sync
```

### Issue: Scraper returns no results

**Solution:** Check that the selected provider's key is set in your `.env` file —
`OPENROUTER_API_KEY` for `LLM_PROVIDER=openrouter`, `CLAUDE_API_KEY` for
`LLM_PROVIDER=anthropic`. The startup log names the one it could not find.

## Next Steps

1. **Start the app**: `uv run python src/ui/app.py`
2. **Set API key**: Edit `.env` and set `OPENROUTER_API_KEY` (or switch
   `LLM_PROVIDER=anthropic` and set `CLAUDE_API_KEY`)
3. **Try a search** with default parameters
4. **Customize** the `.env` file with your preferences
5. **Check README.md** for full documentation

---

**Questions?** Check README.md for comprehensive documentation.
