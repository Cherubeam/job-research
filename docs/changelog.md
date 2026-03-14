# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **Single-page UI**: Removed Results tab — search results now render inline on the Search page as formatted Markdown (no more `max_lines` truncation).
- **Live progress**: Status line updates during search; expandable "Search Log" accordion shows full scraper log history.
- `run_job_research()` is now a generator that streams status/log/result updates to the UI via a background thread.
- CSV output wrapped in a code fence for proper Markdown display.

### Added
- `src/ui/log_capture.py` — thread-safe `LogCaptureHandler` for capturing log messages into the UI.

## [0.3.0] — 2026-03-14

### Added
- `JobSpyScraper` — scraper backend using python-jobspy for Indeed + LinkedIn (no API key needed, no Cloudflare blocking).
- `SCRAPER_BACKEND` env var to switch between `claude` (default) and `jobspy` backends.
- `JobScraper` protocol in `scraper.py` so both scrapers share a common interface.
- Title relevance filtering — rejects results that don't match search keywords.
- Title+company deduplication — collapses identical job postings across locations.
- Work type mapping from JobSpy's `is_remote`/`job_type` columns to human-readable display strings.
- 1.5x overfetch to compensate for filtering, then truncate to `max_jobs`.
- Truncation notice in UI status message when results are cut.
- `total_found` attribute on `JobSpyScraper` for pre-truncation count.
- Final site distribution logged after truncation for debugging multi-source balance.
- Configurable site interleaving (`INTERLEAVE_SITES` env var + UI checkbox) — round-robin mixes results from Indeed and LinkedIn before truncation.
- `scripts/eval_direct_scraper.py` — eval script for JobSpyScraper with optional Claude side-by-side comparison.
- 42 new tests for JobSpyScraper (relevance filtering, dedup, work type mapping, parameter mapping, caching).

### Changed
- Default `MAX_JOBS_PER_SEARCH` raised from 20 to 200.

## [0.2.0] — 2026-03-14

### Added
- File export: search results saved to `data/results/` with timestamped filenames.
- Download button in Results tab to retrieve saved report files.
- Platform adapters (`boards.py`) with per-board URL patterns for deterministic job listing validation.
- `scripts/eval_search_quality.py` — standalone eval script measuring URL match rate and field coverage.
- Prompt rule to skip expired/removed job listings (best-effort filter based on page content markers).

### Changed
- Switch default model from `claude-opus-4-6` to `claude-haiku-4-5-20251001` (~60x cheaper, sufficient for web search + JSON extraction).
- Make `model` parameter required in `ClaudeScraper.__init__` (no more duplicate default).
- Replace job board list with arbeitsagentur.de; remove jobborse.de, wellfound, remote_rocketship, gruenderszene.de.
- Wire JobBoardConfig toggles to scraper so env vars actually enable/disable boards.
- Move site restrictions from query string to `allowed_domains` tool parameter; add `user_location` for German results.
- Convert `JobListing` from dataclass to Pydantic `BaseModel` with runtime validation and salary coercion.
- Merge two-call scraper strategy into single API call — Claude returns structured JSON while search results are still in context.
- System prompt instructs Claude to use multiple searches strategically to find individual job listing pages.
- URL validation uses platform-specific patterns (dual check: URL in search results AND matches job URL pattern).
- Default board config: only Indeed.de enabled for higher-quality results.
- System prompt includes `_max_jobs` count instruction so Claude aims for the configured number of listings.
- Strengthened anti-fabrication prompt wording: "MUST be copied verbatim from a web_search result".
- System prompt instructs Claude to extract ALL job listings, not just cherry-pick based on relevance.
- Salary fields default to null unless explicitly stated in search results.

### Fixed
- Indeed domain mismatch: changed `allowed_domains` from `indeed.de` to `de.indeed.com`.
- Fabricated search results — Claude ignored web_search results and generated fake URLs/data. Now cross-references output against actual search result URLs.
- Zero search results from Indeed search/category page URLs — validation correctly identifies and skips these.
- Scraper retries with a follow-up turn when the model returns narrative text instead of JSON.
- Rate limit handling: disable SDK internal retry, handle 429s with `retry-after` header (default 60s backoff).
- Indeed adapter false positive: removed `jobs?` from URL pattern — `/jobs?q=...` URLs are search pages, not listings.
- Restructure single-call prompt so Claude invokes `web_search` instead of refusing.
- `search_jobs` raises `RuntimeError` with diagnostic message when results are empty.
- Added INFO-level pipeline logging for developer observability.
- Empty search results no longer cached, so failed searches don't block retries for 24h.
- API and scraper errors propagate to the UI instead of being silently swallowed.
- Configure `logging.basicConfig()` in `app.py` so logger output is visible.
- `_claude_web_search` raises on empty text responses; `_parse_results` raises on invalid JSON.
- `app.py` reuses module-level `_config` instead of creating a second `Config()`.
- Cache key includes work_type, seniority_level, and salary range for correct caching.

### Removed
- xing.com from job boards — domain blocks Anthropic's web crawler.

## [0.1.0] — 2026-03-13

### Added
- Claude API scraper using `web_search_20250305` tool
- Gradio web UI with search filters (location, salary, work type, seniority)
- Job analysis and reporting (Markdown + CSV)
- 24h result caching to reduce API costs
- Full pytest test suite (35 tests)
- `docs/` folder with setup, project structure, and scraper design guides

[0.3.0]: https://github.com/Cherubeam/job-research/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Cherubeam/job-research/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/Cherubeam/job-research/releases/tag/v0.1.0
