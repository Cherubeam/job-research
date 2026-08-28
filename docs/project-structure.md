# Project Structure Guide

This document explains what each file does and where to make changes.

---

## Core Architecture

The project is organized into three main layers:

```
┌─────────────────────────────────────────────┐
│         Gradio Web Interface (UI)           │
│              src/ui/app.py                  │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│      Job Research Module (Business Logic)   │
│  config.py | providers.py | scraper.py |    │
│  orchestrator.py | analyzer.py              │
└──────────────┬──────────────────────────────┘
               │
┌──────────────▼──────────────────────────────┐
│       Data Layer (Structure & Storage)      │
│    JobListing | JobSearchParams | Config    │
└─────────────────────────────────────────────┘
```

---

## File-by-File Breakdown

### 1. **src/ui/app.py** - The Web Interface
**What it does:**
- Creates the Gradio web interface that users interact with
- Manages user input and displays results
- Builds the configured `SearchProvider` and the backends at module level from environment config
- Coordinates between the web UI and the business logic

**Key components:**
- `run_job_research()` - Function that executes when user clicks "Search"
- `create_ui()` - Builds the entire web interface
- `main()` - Entry point for the `job-research` CLI command
- Two tabs: Search (with inline results and live log), Info

---

### 2. **src/job_research/config.py** - Configuration Management
**What it does:**
- Defines data structures for all configuration and search parameters
- Handles loading configuration from environment variables (`.env` file)
- Handles loading/saving configuration from/to JSON files
- Provides enums for valid option values (SeniorityLevel, WorkType, OutputFormat)

**Key classes:**
- `SeniorityLevel` - Enum: "Junior", "Mid-level", "Senior", "All levels"
- `WorkType` - Enum: "Remote only", "Remote/Hybrid", "Onsite only", "Any"
- `OutputFormat` - Enum: "markdown", "csv", "json"
- `JobSearchParams` - Data structure for search parameters (keywords, location, salary, etc.)
- `JobBoardConfig` - Which job boards to search
- `OutputConfig` - Output settings (format, directory, caching)
- `Config` - Main configuration class (includes `llm_provider`, `openrouter_api_key`, `openrouter_model`, `claude_api_key`, `claude_model`, `max_jobs_per_search`, `interleave_sites`)
- `LLMProvider` - Enum: "openrouter" (default), "anthropic"
- `ScraperBackend` - Enum: "llm", "jobspy", "bundesagentur" (accepts the legacy value "claude" as "llm")
- `SECRET_FIELDS` - Credential field names, masked in `repr` and dropped from `to_dict()`

---

### 3. **src/job_research/providers.py** - LLM Web-Search Providers
**What it does:**
- Isolates everything vendor-shaped behind one `SearchProvider` protocol
- Returns a `SearchResponse` carrying both the model's text **and** the URLs the
  search actually returned — the scraper needs the second half to reject
  fabricated job links
- Handles per-provider rate limiting and retries (honouring `retry-after`)

**Key classes:**
- `OpenRouterProvider` — OpenRouter's `web` plugin over the OpenAI-compatible
  chat endpoint. Domains via `include_domains`, URLs via `url_citation`
  annotations. Default provider.
- `AnthropicProvider` — the Claude API's server-side `web_search_20250305`
  tool. Domains via `allowed_domains`, URLs via `web_search_tool_result` blocks.
- `SearchResponse`, `SearchProvider`, `ProviderError`

---

### 3b. **src/job_research/scraper.py** - LLM Scraper
**What it does:**
- Implements `LLMScraper` on top of any `SearchProvider` — no vendor SDK here
- Builds the system prompt (including per-source search hints), parses the JSON
  the model returns, and validates every URL against the search results
- Handles caching, keyed on provider and model so a model switch re-fetches

**Key class:** `LLMScraper`
- `search_jobs(params, cache_dir, cache_duration_hours)` → `list[JobListing]`
- `_search_and_extract(query, sources)` → one provider call (search + JSON extraction),
  with a no-search follow-up call when the model answers in prose
- `_validate_listing_urls(listings, urls, sources)` → discard fabricated and search-page URLs

---

### 4. **src/job_research/analyzer.py** - Data Analysis & Reporting
**What it does:**
- Defines the `JobListing` data structure (one job posting)
- Provides the `JobAnalyzer` class to analyze multiple job listings
- Generates reports in Markdown and CSV formats
- Calculates salary statistics, distributions by board/location, etc.

---

### 5. **src/job_research/utils.py** - Utility Functions
**What it does:**
- `create_cache_key()` - Generate cache file names
- `save_cache()` / `load_cache()` - Cache search results to reduce API calls
- `ensure_directories()` - Create required output directories
- `format_salary()` - Format salary range as readable string
- `extract_number_from_text()` - Parse numbers from text

---

### 6. **src/job_research/__init__.py** - Package Initialization
- Exports: `Config`, `JobSearchParams`, `JobAnalyzer`, `LLMScraper`

---

### 7. **pyproject.toml** - Project Configuration
- `[project.dependencies]` includes `anthropic>=0.49.0`
- `[tool.hatch.build.targets.wheel]` configures package discovery (no sys.path hacks needed)
- Entry point: `job-research = "ui.app:main"`

---

### 8. **.env.example** - Configuration Template

**Important variables:**
```
LLM_PROVIDER=openrouter  # openrouter (default) or anthropic
OPENROUTER_API_KEY=      # Required when LLM_PROVIDER=openrouter
OPENROUTER_MODEL=anthropic/claude-haiku-4.5
CLAUDE_API_KEY=          # Required when LLM_PROVIDER=anthropic
CLAUDE_MODEL=claude-haiku-4-5-20251001
MAX_JOBS_PER_SEARCH=200
```

---

## Data Flow Diagram

```
User Input (Gradio UI)
    ↓
app.py: run_job_research()
    ↓
LLMScraper.search_jobs()
    ├─ Check cache (utils.load_cache; keyed on provider + model)
    ├─ _build_search_query() → natural language query
    ├─ _search_and_extract() → one provider.search() call (web search + JSON)
    │   ├─ SearchResponse.result_urls   → ground-truth URLs from the provider
    │   └─ _validate_listing_urls()     → discard fabricated URLs
    ├─ _deduplicate_listings()
    └─ Save cache (utils.save_cache)
    ↓
analyzer.py: JobAnalyzer receives JobListing objects
    ↓
analyzer.py: Generates Markdown/CSV report
    ↓
User sees results
```

---

## Where to Make Common Changes

### Add a new search filter
1. `config.py` — Add field to `JobSearchParams`
2. `app.py` — Add Gradio input component in `create_ui()`
3. `app.py` — Pass parameter to `run_job_research()`

### Change the report format
1. `analyzer.py` — Modify `generate_markdown_report()` or `generate_csv_report()`

### Add support for a new job board
1. `config.py` — Add boolean flag to `JobBoardConfig`
2. `.env.example` — Add environment variable
3. `scraper.py` — Add board to search query construction

### Add new statistics/analysis
1. `analyzer.py` — Add new method to `JobAnalyzer` class
2. `app.py` — Display new statistics in the report

---

## Summary

| File | Purpose |
|------|---------|
| `src/ui/app.py` | Web interface |
| `src/ui/log_capture.py` | Thread-safe log capture for UI |
| `src/job_research/config.py` | Configuration & data structures |
| `src/job_research/providers.py` | OpenRouter / Anthropic web-search providers |
| `src/job_research/scraper.py` | LLM web search scraper |
| `src/job_research/analyzer.py` | Analysis & reporting |
| `src/job_research/utils.py` | Helper functions |
| `pyproject.toml` | Dependencies |
| `.env.example` | Configuration template |
| `scripts/eval_search_quality.py` | Search quality eval (URL match rate) |
| `README.md` | User documentation |
| `docs/setup.md` | Quick setup guide |
