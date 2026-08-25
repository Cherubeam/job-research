# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Bundesagentur für Arbeit backend** (`SCRAPER_BACKEND=bundesagentur`) — Germany's federal job board via its v6 search endpoint. No API key. Off by default; read [ADR-001](decisions/001-bundesagentur-terms-of-use.md) first.
- Structured salary from Bundesagentur (`gehaltsspanneVon`/`Bis`, `festgehalt`) with an explicit period (`verguetungsangabe`), annualised on the way in. Roughly a third of its postings carry pay — more than any other source here exposes.
- `POSTED_WITHIN_DAYS` and a "Posted within (days)" UI field. Bundesagentur applies it server-side via `veroeffentlichtseit`; other backends filter locally. Listings with no parseable date are kept.
- `scripts/probe_bundesagentur.py` — manual field-mapping check against the live endpoint, separating required from optional fields. The test suite itself never touches the network.
- `tests/test_bundesagentur.py` — 30 tests against fixtures recorded from real v6 responses, including the ADR-001 page ceiling.
- `src/job_research/sources/` — a source registry declaring, per board: id, label, domain, which backends can reach it, its listing-URL pattern, whether it is on by default, and any caveat.
- `ENABLED_SOURCES` env var and a **Job Sources** picker in the UI, offering only sources the active backend can actually search. Sources with a caveat are flagged.
- `tests/test_catalog.py` — registry integrity checks (unique ids, jobspy sources declare a site name, defaults work on both backends, Arbeitsagentur stays off by default).
- `src/job_research/pipeline/` — package split into `relevance.py`, `dedup.py`, `filters.py`, `interleave.py`.
- **Relevance scoring** replaces the single-token match: a title must cover more than half of some search phrase (`RELEVANCE_THRESHOLD`, default 0.6). "Sales Engineer" no longer matches "AI Engineer".
- **Negative keywords** (`EXCLUDED_KEYWORDS` + a UI field) drop matching titles outright, matched on whole words so "sales" does not reject "Salesforce".
- `src/job_research/salary.py` — salary parsing with period detection; hourly and monthly pay is annualised (40h x 52 for hourly).
- `tests/test_relevance.py`, `tests/test_dedup.py`, `tests/test_salary.py`.
- `src/job_research/pipeline.py` — shared post-fetch stage: salary filter, seniority filter, board interleaving, truncation. Applies to every backend.
- Salary filtering by range overlap; listings that state no salary are kept, since most German postings omit it.
- Seniority filtering, inferred from the job title, including German compounds ("Teamleiter", "Abteilungsleitung").
- `tests/test_pipeline.py` and `tests/test_app.py` — including a deterministic regression test for concurrent searches sharing parameters.
- GitHub Actions CI (`.github/workflows/ci.yml`) — ruff, black, mypy, and pytest on every push and pull request.
- `tests/test_characterization.py` — 23 tests pinning current behaviour ahead of the planned refactors, including known-wrong behaviour marked `test_characterizes_*`.
- `.git-blame-ignore-revs` so the bulk black reformatting commit does not obscure `git blame`.
- `pandas-stubs` dev dependency.
- `docs/architecture-review.md` — architecture review with findings (F1–F13) and a phased refactor plan.
- `docs/decisions/` — ADR folder; ADR-001 records the Bundesagentur für Arbeit access posture and ADR-002 the LinkedIn scraping posture (both opt-in, off by default).
- `src/ui/log_capture.py` — thread-safe `LogCaptureHandler` for capturing log messages into the UI.

### Changed
- Bundesagentur postings restrict to `angebotsart=1` (ARBEIT), excluding apprenticeships, dual study places, and self-employment offers.
- **The jobspy backend honours the source selection** instead of hardcoding `["linkedin", "indeed"]`, so the board toggles are no longer fiction for the default backend (F2).
- `JobBoardConfig` and its seven booleans removed; `boards.py` folded into the registry. `SEARCH_*` env vars still work with a deprecation warning when `ENABLED_SOURCES` is unset.
- `ClaudeScraper` no longer takes `board_config`; sources are resolved per search, so a selection change no longer needs a new scraper.
- `Config.to_dict` is generated from `fields()` and excludes `claude_api_key` — the hand-written version had already drifted, missing four fields.
- **Indeed is the only default-on source.** LinkedIn is now opt-in ([ADR-002](decisions/002-linkedin-scraping.md)): scraping it breaches its User Agreement, and on a rate-limit block python-jobspy returns partial results that are indistinguishable from a thin search.
- `linkedin_fetch_description` disabled — it issued one extra request per job for descriptions LinkedIn's signup wall usually withholds.
- **One deduplication rule for every backend.** The two scrapers previously disagreed: Claude keyed on URL alone (so a cross-posted job survived twice) and jobspy on title+company (so the same role in two cities collapsed into one). Now: normalized URL, then title + company + normalized location.
- Relevance filtering and deduplication moved out of the scrapers into the pipeline, so both apply to every backend.
- **Salary and seniority now actually filter results.** They previously reached only the cache key, so adjusting them forced a full re-fetch that returned identical listings.
- Scrapers return the full deduplicated fetch; filtering, interleaving, and truncation moved out of them into `pipeline.apply`.
- `create_cache_key` takes named fetch inputs (`create_cache_key(backend, **inputs)`) and covers only what the backend actually received. Salary and seniority are out; `max_jobs` and the board list are in, so raising `MAX_JOBS_PER_SEARCH` re-fetches instead of replaying a truncated cached set.
- `run_job_research` builds per-request `JobSearchParams` instead of mutating the module-level config.
- CSV output is written with the stdlib `csv` module.
- Status line distinguishes fetched, matched, and shown counts.
- README and the UI's Info tab describe the pipeline that exists, not an aspirational one.
- Version is single-sourced from package metadata via `importlib.metadata`; `__init__.py` no longer hardcodes it (was stale at 0.1.0).
- Whole codebase formatted with black so the CI format gate is enforceable.
- Analyzer tests assert exact values instead of `is not None` / `min <= max`.
- **Single-page UI**: Removed Results tab — search results now render inline on the Search page as formatted Markdown (no more `max_lines` truncation).
- **Live progress**: Status line updates during search; expandable "Search Log" accordion shows full scraper log history.
- `run_job_research()` is now a generator that streams status/log/result updates to the UI via a background thread.
- CSV output wrapped in a code fence for proper Markdown display.

### Security
- `Config.__repr__` masks `claude_api_key` (`sk-ant-…mPoQAA`), so a traceback, log line, or bug report cannot leak it. Pytest's assertion repr was observed printing the key from a failing test that touched a `Config`.

### Fixed
- Salary parsing no longer reads contract hours or a posting year as a salary bound: `"35 Std./Woche, 60.000 €"` was `(35, 60000)`, now `(60000, None)`; `"2026: 70.000 - 95.000 €"` was `(2026, 70000)`, now `(70000, 95000)` (F7).
- Monthly and hourly pay are annualised instead of being compared against annual bounds (F7).
- Concurrent searches no longer overwrite each other's parameters (F4): two browser tabs could run each other's query.
- CSV no longer corrupts fields containing quotes, commas, or newlines (F8).
- Truncation now happens after filtering, so a filtered search returns up to `MAX_JOBS_PER_SEARCH` results instead of fewer.
- `hasattr`/`getattr` duck-typing on scraper internals removed from `app.py`; both backends now satisfy the `JobScraper` protocol unchanged (F5, F10).
- `_safe_int` in `jobspy_scraper.py` now narrows on `SupportsFloat`; narrowing on `(int, float)` would have dropped every salary from an all-integer pandas column, since `numpy.int64` subclasses neither.
- All 8 mypy errors resolved; `uv run mypy src/` is clean.

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
