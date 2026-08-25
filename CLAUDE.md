# Job Research Tool — Claude Code Context

## What This Project Does

AI/ML job research tool that searches German job boards via the **Anthropic Claude API** (`web_search_20250305` tool). Results are analyzed and displayed in a Gradio web UI.

## How to Run

```bash
uv run python src/ui/app.py
# or after uv pip install -e .:
uv run job-research
```

Opens at **http://127.0.0.1:7860**

Custom port: `GRADIO_SERVER_PORT=7861 uv run python src/ui/app.py`

## Key Architecture

```
src/job_research/   ← core logic package
  config.py         ← Config dataclass + env loading
  scraper.py        ← ClaudeScraper (web_search_20250305)
  analyzer.py       ← JobListing + JobAnalyzer + reports
  utils.py          ← cache, salary formatting, text parsing

src/ui/
  app.py            ← Gradio UI + entry point (main())
```

**Data flow:** Gradio UI → `run_job_research()` → `ClaudeScraper.search_jobs()` → `JobAnalyzer` → report string displayed in UI.

## Critical Environment Variables

```bash
CLAUDE_API_KEY=      # Required — scraper won't work without it
CLAUDE_MODEL=claude-haiku-4-5-20251001  # Optional, default: claude-haiku-4-5-20251001
MAX_JOBS_PER_SEARCH=20         # Optional, default: 20
```

Copy `.env.example` → `.env` and fill in `CLAUDE_API_KEY`.

## Dev Commands

```bash
uv sync                        # install/update deps
uv pip install -e .            # editable install (removes sys.path hacks)
uv run pytest tests/ -v        # run tests
uv run ruff check src/ tests/  # lint
uv run black src/              # format
uv run mypy src/               # type check
```

## Docs

- `docs/setup.md` — installation guide
- `docs/project-structure.md` — file-by-file breakdown
- `docs/scraper-design.md` — scraper architecture decisions
- `docs/changelog.md` — version history
- `research/` — reference material on German job boards

## Package Management

Always use `uv`, never `pip` directly:
- `uv sync` — install/update all deps (runtime + dev group)
- `uv add <pkg>` — add runtime dependency
- `uv add --dev <pkg>` — add dev dependency
- `uv remove <pkg>` — remove dependency

## Git Workflow

### Branching
Each feature, fix, or change gets its own branch:
```bash
git checkout -b feature/short-description   # new feature
git checkout -b fix/short-description       # bug fix
git checkout -b docs/short-description      # documentation only
git checkout -b chore/short-description     # tooling, deps, config
```

### Commits
Use short conventional commit messages:
```
feat: add salary range filter to UI
fix: handle empty API response in scraper
docs: update setup guide for uv sync
chore: bump anthropic to 0.50.0
test: add edge cases for _normalize_salary
refactor: extract query builder to separate method
```

Run `uv run ruff check src/ tests/` before committing to catch issues early.

CI enforces four gates on every push and PR: `ruff check`, `black --check`,
`mypy src/`, and `pytest`. All four must pass before merging.

When implementing changes, commit each logical step as you go with a single-sentence commit message.

### Finishing a feature branch
Before merging:
1. Review and update any affected files in `docs/` and `README.md`
2. Add an entry to `docs/changelog.md` under `[Unreleased]`
3. Merge into `main` using fast-forward where possible:
   ```bash
   git checkout main
   git merge --ff-only feature/short-description
   ```
   If fast-forward isn't possible (diverged history), rebase first:
   ```bash
   git rebase main feature/short-description
   git checkout main && git merge --ff-only feature/short-description
   ```

### Releases and tags
When cutting a release:
1. Move `[Unreleased]` entries in `docs/changelog.md` to a new versioned section
2. Bump `version` in `pyproject.toml`
3. Commit: `chore: release v0.2.0`
4. Tag: `git tag v0.2.0`

Tag significant releases (new features, breaking changes). Patch fixes can be tagged or skipped at your discretion.

### Test coverage
Run `uv run pytest tests/ --cov=job_research` when adding new modules to track coverage.
