# Changelog

All notable changes to this project will be documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- File export: search results are saved to `data/results/` with timestamped filenames
- Download button in Results tab to retrieve saved report files

### Fixed
- Empty search results are no longer cached, so failed searches don't block retries for 24h
- API and scraper errors now propagate to the UI instead of being silently swallowed
- Configure `logging.basicConfig()` in `app.py` so logger output is actually visible

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
