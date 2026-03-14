# Scraper Architecture - Design Document

**Status:** Implemented
**Created:** November 21, 2025
**Updated:** March 2026
**Version:** 4.0

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
    ├─ _build_search_query() — format search terms
    ├─ _search_and_extract() — single API call: web search + JSON extraction
    │   ├─ _build_system_prompt() — platform-specific search guidance
    │   ├─ _extract_search_result_urls() — ground-truth URLs
    │   └─ _validate_listing_urls() — dual check: in search results + job URL pattern
    ├─ _deduplicate_listings()
    └─ Save cache (utils.save_cache)
    ↓
analyzer.py: JobAnalyzer
    ├─ Analyzes job listings
    └─ Generates Markdown/CSV reports
    ↓
User sees results
```

### 2.2 Single-Call Strategy

**`_search_and_extract(query)`** — one API call with `web_search_20250305` tool:
- Uses `tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": 10, "allowed_domains": [...], "user_location": {"type": "approximate", "country": "DE"}}]`
- Site restrictions are handled via `allowed_domains` on the tool (not in the query string)
- `user_location` is set to Germany for localized results
- **System message** contains behavioral/formatting instructions (JSON output format, `_max_jobs` count target, anti-fabrication rules)
- **User message** is a simple search request — this separation prevents Claude from treating JSON instructions as the primary request and skipping tool invocation
- Strips accidental markdown fences; falls back to regex `\[.*\]` extraction if direct `json.loads` fails
- Each extracted item is validated via Pydantic `JobListing(**item)` — invalid items are skipped with a log message

### 2.3 URL Validation with Platform Adapters

The API response contains `web_search_tool_result` blocks with real URLs from the search. However, not all search result URLs are individual job listings — many are search/category pages (e.g., `indeed.de/AI-Engineer-Jobs-in-Berlin`). After extracting Claude's JSON output, validation applies a dual check:

1. `_extract_search_result_urls()` collects all URLs from `web_search_tool_result` blocks as ground truth
2. `_validate_listing_urls()` keeps only listings that pass **both** checks:
   - **In search results:** the `job_url` matches a ground-truth URL (prevents fabrication)
   - **Matches job URL pattern:** the URL matches the platform adapter's individual job page pattern (prevents search-page URLs from being treated as listings)
3. URL normalization strips fragments and trailing slashes while preserving query params

Platform adapters (`boards.py`) define per-board URL patterns:
- **Indeed:** `/viewjob`, `/rc/clk` — rejects `/jobs?q=...` search pages and `/AI-Engineer-Jobs-in-Berlin`
- **StepStone:** `/stellenangebote--`, `/jobs/<id>` — rejects search listing pages
- **LinkedIn:** `/jobs/view/<id>` — rejects `/jobs/search/`
- **Fallback:** unknown boards accept any URL on their domain

The system prompt also includes platform-specific guidance so Claude uses follow-up searches to find individual job pages when initial results return only search/category pages.

### 2.4 Board Coverage

**Default:** `de.indeed.com` only (largest German job aggregator, no login required). Other boards (StepStone, LinkedIn, Monster, Honeypot, startup.jobs, Arbeitsagentur) can be re-enabled via UI toggles or env vars. Focusing on a single board reduces scope and improves result quality.

### 2.5 Pydantic Validation

`JobListing` is a Pydantic `BaseModel` (not a dataclass). This provides:
- **Title validation:** empty/whitespace titles raise `ValidationError`, skipping the item
- **Salary coercion:** string salaries (`"€70.000"`, `"90k"`) are parsed via a `model_validator`
- **Type safety:** all fields get runtime type checking and defaults

---

## 3. Key Design Decisions

### 3.1 Search Query Construction

Builds a simple natural language query (site restrictions are handled by `allowed_domains` on the tool config):

```python
query = f"{keywords} in {location} ({work_type})"
# Site restrictions moved to allowed_domains in tool config
# user_location set to DE for German results
```

**Example query:**
```
AI Engineer in Berlin Remote
```

### 3.2 Caching Strategy

- **Cache key:** `create_cache_key("claude_web_search", keywords, location)`
- **Cache location:** `data/cache/{key}.json`
- **Cache duration:** `CACHE_DURATION_HOURS` (default 24h)
- Salary is NOT part of the cache key — filtering is client-side

### 3.3 Rate Limiting and Retries

- Minimum 2 seconds between API calls (`_rate_limit()`)
- 3 retries with exponential backoff (1s, 2s, 4s) on `anthropic.APIStatusError`
- `search_jobs()` raises `RuntimeError` on empty/invalid results — the UI displays the specific error

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
MAX_JOBS_PER_SEARCH=20        # Optional, soft cap (actual count depends on search results)
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

**Typical search (1 API call):**
- Input: ~600 tokens (query + web results context)
- Output: ~1500 tokens (JSON listings)
- Cost: ~$0.001-0.002 per search at haiku-4-5 pricing

**Monthly estimate (1-2 users with caching):**
- Conservative (50 searches/month): ~$0.50-1
- Active (200 searches/month): ~$2-4

**Caching reduces costs by 50-70%** for repeated searches.

---

## 6. JobSpyScraper (Indeed + LinkedIn)

### 6.1 Why JobSpy?

The `ClaudeScraper` uses Claude's `web_search_20250305` tool for both fetching and extracting job data. This works but has trade-offs: expensive per search, low yield (1-4 listings from dozens of URLs), and tightly coupled to the Anthropic SDK.

**JobSpy** (python-jobspy) hits Indeed's **mobile app API** and LinkedIn — not the Cloudflare-protected websites — which is why it works without proxies, rate limiting, or browser automation. It returns structured DataFrame rows directly, making Claude's web search role redundant for the fetching step.

### 6.2 Architecture

```
SCRAPER_BACKEND=jobspy

User Input (Gradio UI)
    ↓
app.py: selects JobSpyScraper based on config
    ↓
jobspy_scraper.py: JobSpyScraper.search_jobs()
    ├─ Check cache (utils.load_cache)
    ├─ _scrape() → jobspy.scrape_jobs(site_name=["indeed", "linkedin"], ...)
    │   ├─ Overfetch 1.5x results_wanted
    │   ├─ _to_job_listing() — DataFrame row → JobListing (maps work_type, job_board)
    │   └─ _is_relevant() — title token matching against keywords + alternatives
    ├─ _deduplicate() — URL + title+company dedup
    ├─ _interleave_by_site() — round-robin mix (if enabled)
    ├─ Truncate to max_jobs
    └─ Save cache (utils.save_cache)
    ↓
analyzer.py: JobAnalyzer (same as Claude path)
```

### 6.3 Result Quality Pipeline

Raw JobSpy results contain irrelevant titles and duplicates. Three post-processing steps:

1. **Title relevance filtering** (`_is_relevant()`): Tokenizes search keywords + `job_title_alternatives`, rejects listings whose title shares zero non-stopword tokens. Catches "Shopify Backend Developer" when searching "AI Engineer".

2. **Title+company deduplication** (`_deduplicate()`): Groups by `(title.lower(), company.lower())` — same job posted in multiple locations (with different URLs) is kept only once. Also deduplicates by exact URL.

3. **Overfetch + truncate**: Requests `max_jobs * 1.5` from JobSpy to compensate for filtering losses, then truncates to `max_jobs`.

4. **Site interleaving** (`_interleave_by_site()`): Round-robin interleaves listings from different job boards before truncation. Without this, the site returning more results (typically Indeed) dominates the output. Configurable via `INTERLEAVE_SITES` env var (default: true) and a UI checkbox.

### 6.4 Configuration

```bash
SCRAPER_BACKEND=jobspy           # or "claude" (default)
MAX_JOBS_PER_SEARCH=200          # passed to results_wanted (internally 1.5x)
INTERLEAVE_SITES=true            # round-robin mix results from different sites (default: true)
```

No API key needed for the `jobspy` backend.

### 6.5 JobScraper Protocol

Both scrapers implement the same `JobScraper` protocol:

```python
class JobScraper(Protocol):
    def search_jobs(
        self, params: JobSearchParams, cache_dir: Path,
        cache_duration_hours: int = 24,
    ) -> list[JobListing]: ...
```

### 6.6 Work Type Mapping

**Search filters** (passed to JobSpy):

| WorkType     | jobspy param          |
|-------------|----------------------|
| Remote only  | `is_remote=True`     |
| Onsite only  | `is_remote=False`    |
| Hybrid / Any | no filter (all results) |

**Result mapping** (from JobSpy columns to `JobListing.work_type`):

| JobSpy columns              | work_type display |
|----------------------------|------------------|
| `is_remote=True`           | "Remote"         |
| `job_type="fulltime"`      | "Full-time"      |
| `job_type="parttime"`      | "Part-time"      |
| `job_type="contract"`      | "Contract"       |
| `job_type="internship"`    | "Internship"     |
| neither set                | "" (Unknown)     |

### 6.7 Trade-offs vs Claude Scraper

| Aspect         | JobSpyScraper       | ClaudeScraper |
|---------------|--------------------:|-------------:|
| Cost           | Free               | ~$0.002/search |
| API key needed | No                 | Yes          |
| Listing yield  | 10-20 per search   | 1-4 per search |
| Data quality   | Structured (from API) | LLM-extracted |
| Board coverage | Indeed + LinkedIn  | Configurable  |
| Salary data    | When available     | Often missing  |
| Descriptions   | Full text          | Not available  |
| Work type      | From API columns   | LLM-guessed   |

---

## 7. Future Enhancements

- **OpenRouter migration**: Replace Anthropic SDK with OpenRouter for LLM analysis (report generation, semantic filtering)
- **LLM analysis layer**: Use LLM for report summarization, career matching — features where deterministic scraping can't help
- **Better salary parsing**: Extend Pydantic validators for more complex formats
- **Company research**: Pull company info from additional sources
- **Scheduled searches**: Cron-based job alerts
