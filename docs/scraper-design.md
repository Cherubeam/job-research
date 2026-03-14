# Claude-Assisted Web Search Scraper - Design Document

**Status:** Implemented
**Created:** November 21, 2025
**Updated:** March 2026
**Version:** 2.0

---

## 1. Overview

This document outlines the design for the Claude-assisted web search integration in the Job Research Tool.

**Why Claude Web Search (`web_search_20250305` tool)?**
- No direct job-board scraping — no blocking risk
- Anthropic's infrastructure handles all fetching
- No API partnerships or rate limiting concerns
- Handles complex natural language queries
- Automatic coverage of multiple German job boards
- Cost-effective for 1-2 users (~$1-5/month)

---

## 2. Architecture

### 2.1 High-Level Flow

```
User Input (Gradio UI)
    ↓
app.py: run_job_research()
    ├─ Validates inputs
    ├─ Checks _scraper is initialized
    ↓
scraper.py: ClaudeScraper.search_jobs()
    ├─ Check cache (utils.load_cache)
    ├─ _build_search_query() — format natural language query
    ├─ _claude_web_search()  — API call #1: web_search tool
    ├─ _parse_results()      — API call #2: JSON extraction
    ├─ _deduplicate_listings()
    └─ Save cache (utils.save_cache)
    ↓
analyzer.py: JobAnalyzer
    ├─ Analyzes job listings
    └─ Generates Markdown/CSV reports
    ↓
User sees results
```

### 2.2 Two-Call Strategy

**Call #1: `_claude_web_search(query)`**
- Uses `tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}]`
- Claude searches the web and returns text with job listings
- Collects all `type == "text"` content blocks from the response

**Call #2: `_parse_results(raw_response, params)`**
- No tools — plain text completion
- Instructs Claude to extract a JSON array from the web search text
- Strips accidental markdown fences with `re.sub` before `json.loads`
- On `JSONDecodeError` → logs warning and returns `[]`

---

## 3. Key Design Decisions

### 3.1 Search Query Construction

Builds a natural language query with site operators:

```python
query = f"{keywords} in {location} ({work_type})"
site_clause = "site:stepstone.de OR site:indeed.de OR ..."
instruction = f"Find approximately {max_jobs} job listings. Return JSON array."
```

**Example output:**
```
AI Engineer in Berlin Remote (site:stepstone.de OR site:indeed.de OR site:linkedin.com
OR site:xing.com OR site:monster.de OR site:jobborse.de OR site:honeypot.io
OR site:startup.jobs OR site:gruenderszene.de).
Find approximately 20 job listings. Return results as JSON array with fields:
title, company, location, salary_min, salary_max, work_type, job_board, job_url.
```

### 3.2 Caching Strategy

- **Cache key:** `create_cache_key("claude_web_search", keywords, location)`
- **Cache location:** `data/cache/{key}.json`
- **Cache duration:** `CACHE_DURATION_HOURS` (default 24h)
- Salary is NOT part of the cache key — filtering is client-side

### 3.3 Rate Limiting and Retries

- Minimum 2 seconds between API calls (`_rate_limit()`)
- 3 retries with exponential backoff (1s, 2s, 4s) on `anthropic.APIStatusError`
- All exceptions caught in `search_jobs()` — returns `[]` instead of crashing the UI

### 3.4 Deduplication

- Primary: dedup by URL (if present and non-empty)
- Fallback: dedup by `title.lower() + "|" + company.lower()`

### 3.5 Salary Normalization

Handles multiple formats:
- `"€80.000 – 120.000"` (European decimal separator)
- `"70k-100k"` (abbreviated)
- `"ab 80000 EUR"` (German prefix)
- `""` / `None` → `(None, None)`

---

## 4. Configuration

### Environment Variables

```bash
CLAUDE_API_KEY=sk-ant-...     # Required
CLAUDE_MODEL=claude-haiku-4-5-20251001  # Optional, defaults to opus-4-6
MAX_JOBS_PER_SEARCH=20        # Optional, default 20
CACHE_DURATION_HOURS=24       # Optional
```

### Config Dataclass Fields

Added to `Config` in `config.py`:
```python
claude_api_key: Optional[str] = None
claude_model: str = "claude-haiku-4-5-20251001"
max_jobs_per_search: int = 20
```

---

## 5. Cost Estimation

**Typical search (2 API calls):**
- Input: ~600 tokens (query + web results context)
- Output: ~1500 tokens (parsed JSON listings)
- Cost: ~$0.001-0.003 per search at haiku-4-5 pricing

**Monthly estimate (1-2 users with caching):**
- Conservative (50 searches/month): ~$1-2
- Active (200 searches/month): ~$4-8

**Caching reduces costs by 50-70%** for repeated searches.

---

## 6. Future Enhancements

- **Arbeitsagentur API**: Add parallel source alongside Claude search
- **Better salary parsing**: Use Claude itself to normalize complex formats
- **Company research**: Pull company info from additional sources
- **Job description analysis**: Claude summarization of key requirements
- **Scheduled searches**: Cron-based job alerts
