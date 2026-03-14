# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Indeed adapter false positive: removed `jobs?` from URL pattern — `/jobs?q=...` URLs are search pages, not individual listings.
- Eval script crash when Claude returns narrative text instead of JSON — now retries with a follow-up extraction request (same pattern as `scraper.py`).
- System prompt search guidance now gives actionable follow-up strategy: search for `"[company] [title] site:[domain]"` when initial results are search/category pages.
- Indeed `search_hint` updated with concrete example and valid URL path patterns.

### Added
- Prompt rule to skip expired/removed job listings (best-effort filter based on page content markers like "abgelaufen", "nicht mehr verfügbar").

### Changed
- System prompt now includes `_max_jobs` count instruction so Claude aims for the configured number of listings (default 20) instead of defaulting to ~10.
- Strengthened anti-fabrication prompt wording: "MUST be copied verbatim from a web_search result" replaces the weaker "Use the EXACT URL" instruction.

### Added
- Platform adapters (`boards.py`) with per-board URL patterns for deterministic job listing validation — distinguishes individual job pages from search/category pages.
- `scripts/eval_search_quality.py` — standalone eval script measuring URL match rate and field coverage, now with adapter-based URL classification.

### Changed
- System prompt instructs Claude to use multiple searches strategically to find individual job listing pages (not just search/category pages).
- URL validation uses platform-specific patterns (dual check: URL must be in search results AND match a job URL pattern) instead of exact URL matching only.
- Default board config: only Indeed.de enabled (others can be re-enabled via UI). Reduces scope for higher-quality results.
- Prompt no longer requests a specific result count — returns however many real listings are found.
- Salary fields default to null unless explicitly stated in search results.

### Fixed
- Indeed domain mismatch: changed `allowed_domains` from `indeed.de` to `de.indeed.com` — individual job pages (`/viewjob`) live on `de.indeed.com`, not `indeed.de`, so searches restricted to `indeed.de` could only return category/search pages.
- Search results were entirely fabricated — Claude ignored web_search results and generated fake URLs/data. Now cross-references output against actual search result URLs and discards fabricated listings.
- Zero search results when `web_search` returns Indeed search/category page URLs instead of individual job pages — new validation correctly identifies and skips these.

### Fixed
- Scraper now retries with a follow-up turn when the model returns narrative text instead of JSON, instead of immediately failing with `RuntimeError`
- Fix follow-up retry hitting rate limits: disable SDK's internal retry (`max_retries=0`), handle 429s with `retry-after` header (default 60s backoff) instead of 1–4s exponential backoff

### Removed
- xing.com from job boards — domain blocks Anthropic's web crawler, incompatible with `allowed_domains`

### Added
- File export: search results are saved to `data/results/` with timestamped filenames
- Download button in Results tab to retrieve saved report files

### Fixed
- Restructure single-call prompt so Claude invokes `web_search` instead of refusing — separate system message (formatting instructions) from user message (search request)

### Changed
- Move site restrictions from query string to `allowed_domains` tool parameter; add `user_location` for German results
- Convert `JobListing` from dataclass to Pydantic `BaseModel` with runtime validation and salary coercion
- Merge two-call scraper strategy into single API call — Claude now returns structured JSON while search results are still in context, fixing information loss between calls

### Fixed
- `search_jobs` now raises `RuntimeError` with a diagnostic message when results are empty, distinguishing "no items extracted" from "all items filtered" — the UI shows the specific reason instead of a generic message
- Added INFO-level pipeline logging (web search size, parsed count, dedup count, skipped items) for developer observability
- Removed dead `if not listings` branch in `app.py` (now handled by exception)
- Empty search results are no longer cached, so failed searches don't block retries for 24h
- API and scraper errors now propagate to the UI instead of being silently swallowed
- Configure `logging.basicConfig()` in `app.py` so logger output is actually visible
- `_claude_web_search` now raises on empty text responses instead of silently returning `""`
- `_parse_results` raises on invalid JSON and non-array responses instead of returning `[]`
- `_listing_from_dict` logs skipped items (missing title) at debug level
- `app.py` reuses the module-level `_config` instead of creating a second `Config()` with different defaults
- Empty-result UI message now provides actionable troubleshooting hints

### Changed
- Switch default model from `claude-opus-4-6` to `claude-haiku-4-5-20251001` (~60x cheaper, sufficient for web search + JSON extraction)
- Make `model` parameter required in `ClaudeScraper.__init__` (no more duplicate default)
- Replace job board list with arbeitsagentur.de (Germany's largest job portal); remove jobborse.de, wellfound, remote_rocketship, gruenderszene.de
- Wire JobBoardConfig toggles to scraper so env vars actually enable/disable boards

### Fixed
- Cache key now includes work_type, seniority_level, and salary range so different filter combinations no longer return stale cached results

## [0.1.0] — 2026-03-13

### Added
- Claude API scraper using `web_search_20250305` tool
- Gradio web UI with search filters (location, salary, work type, seniority)
- Job analysis and reporting (Markdown + CSV)
- 24h result caching to reduce API costs
- Full pytest test suite (35 tests)
- `docs/` folder with setup, project structure, and scraper design guides

[0.1.0]: https://github.com/Cherubeam/job-research/releases/tag/v0.1.0
