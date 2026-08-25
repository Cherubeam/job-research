# Architecture Review & Refactor Plan

**Date:** 2026-08-25
**Reviewed version:** 0.3.0 (+ unreleased single-page UI work)
**Scope:** result quality, reliability, and adaptability for planned enhancements

---

> **Progress:** Phases 0, 1, and 2 are merged. Phase 3 (source registry) is next.
> Findings still open: F2 (jobspy hardcodes its board list), F11 (no persistence),
> F12 (documentation drift — corrected as each phase lands).

## 1. Verdict

The project is in better shape than its size suggests. The seams are in roughly
the right places — a `JobScraper` Protocol, a Pydantic `JobListing` as the shared
contract, per-board URL adapters — so this is a **refactor, not a rewrite**.

Three things hold it back today:

1. **Features that are advertised but not implemented.** Two of the four search
   filters do nothing; the board toggles do nothing for the backend you'd
   actually use. The README and Info tab describe a quality pipeline that does
   not exist as code.
2. **Quality logic lives inside the scrapers.** Dedup is implemented twice, with
   different semantics. Relevance filtering exists in one backend only. There is
   nowhere to put a shared filter, which is *why* items in (1) were never built.
3. **No memory between runs.** Every search is a fresh one-shot. For a tool used
   actively, the valuable question is "what changed since yesterday" — and
   nothing in the current data model can answer it.

---

## 2. What works and should be preserved

**Anti-fabrication validation in `ClaudeScraper`.** Extracted URLs are checked
against the actual `web_search_tool_result` blocks
([scraper.py:203](../src/job_research/scraper.py)) and then against a per-board
URL *shape* pattern ([scraper.py:217](../src/job_research/scraper.py)). Ground
truth comes from the tool result, never from the model's prose. This is the
single most valuable piece of engineering in the repo and must survive every
refactor below.

**Operational hygiene.** SDK retries disabled in favour of explicit
`retry-after` handling; failed searches deliberately not cached; cache entries
carry expiry; INFO-level logging that surfaces into the UI.

**Test suite.** 133 tests, fully mocked, 1.4s. The jobspy fixture exercises real
edge cases (`np.nan` in title, salary, and date columns). Parameter-mapping tests
assert concrete kwargs rather than "it was called".

**Documentation discipline.** The changelog is detailed and honest about fixes.
The `research/` corpus is genuinely useful input (though now partly stale).

---

## 3. Findings

Ordered by impact. Each maps to a phase in §5.

### F1 — Seniority and salary filters are inert (Phase 1) — RESOLVED

`seniority_level`, `salary_minimum`, and `salary_maximum` flow from the UI into
`create_cache_key()` and **nowhere else**. Neither backend filters on them.

This is worse than a no-op: because they participate in the cache key, adjusting
the salary slider invalidates the cache and forces a full re-fetch that returns
byte-identical results. The user pays latency (and, on the Claude backend, money)
for a change that cannot affect the outcome.

### F2 — The jobspy backend ignores board configuration (Phase 3)

`site_name` is hardcoded to `["linkedin", "indeed"]`
([jobspy_scraper.py:132](../src/job_research/jobspy_scraper.py)). All seven
`SEARCH_*` environment variables are dead for this backend. The Info tab
advertises StepStone, XING, Monster, and Arbeitsagentur; XING was removed in
0.2.0 and never restored.

### F3 — Relevance filtering is a single-token OR (Phase 2) — RESOLVED

`_is_relevant` keeps any title sharing **one** token with the keyword set. With
the default alternatives that set is
`{ai, engineer, machine, learning, artificial, intelligence, deep, ml}`, so
"Sales Engineer", "Bauingenieur", and "Learning & Development Manager" all pass.

This is the highest-leverage single change for **result quality**. It needs a
score (exact phrase > token overlap), a threshold, and a negative-keyword list.

### F4 — Global mutable state races with the background thread (Phase 1) — RESOLVED

`_config` is module-level. `run_job_research` mutates `_config.search_params` in
place ([app.py:79](../src/ui/app.py)) and then hands that same object to a daemon
thread. Two browser tabs, or one double-click, and search A executes with search
B's parameters. Fix: construct a fresh `JobSearchParams` per request.

### F5 — The scraper seam leaks (Phase 2) — RESOLVED

[app.py:92](../src/ui/app.py) duck-types on a *private method*
(`hasattr(_scraper, "_interleave_by_site")`) to decide whether to pass
`interleave`, because the Protocol does not carry it.

The fix is not to widen the Protocol. Interleaving, dedup, relevance, and
truncation are **not scraper concerns**. Today dedup exists twice with different
semantics — `ClaudeScraper` dedups by URL *or* title+company, `JobSpyScraper` by
title+company *and* URL — so the two backends silently disagree about what a
duplicate is.

### F6 — Cache stores post-truncation results (Phase 1) — RESOLVED

`JobSpyScraper` interleaves and truncates *before* writing the cache. Raising
`MAX_JOBS_PER_SEARCH` returns the old, smaller set for 24 hours. The cache should
hold the normalized full fetch; truncation and interleaving are view concerns.

### F7 — Salary parsing is unanchored (Phase 2) — RESOLVED

`_parse_salary_range` takes the first two integers found in the string, with no
unit or period detection. `"35 Std./Woche, 60.000 €"` yields `(35, 60000)`. The
README claims normalization across annual/monthly/hourly; no such logic exists.
Related: `if listing.salary_min and ...` treats a legitimate `0` as missing.

### F8 — Hand-rolled CSV without escaping (Phase 1) — RESOLVED

[analyzer.py:231](../src/job_research/analyzer.py) builds CSV with f-strings. Any
title or company containing a double quote produces malformed output. Use the
stdlib `csv` module.

### F9 — No CI; mypy currently fails (Phase 0) — RESOLVED

`uv run mypy src/` reports 8 errors despite being documented in `CLAUDE.md`.
There is no `.github/` at all. Every phase below is a refactor, and refactoring
without an enforced gate is refactoring blind.

### F10 — Backend behaviour diverges silently (Phase 2) — RESOLVED in Phase 1

`ClaudeScraper` never truncates to `max_jobs` (it is a prompt hint only) and
exposes no `total_found`, so [app.py:149](../src/ui/app.py)'s
`getattr(_scraper, "total_found", …)` reports differently depending on which
backend is active.

### F11 — No stable identity, no persistence (Phase 5a)

`JobListing` has no id, no `source_id`, and `posted_date` is an unparsed `str`.
Each run writes a timestamped file and forgets everything. Nothing can answer
"is this new?" or "did I already dismiss this?".

### F12 — Documentation drift

`__init__.py` declares `0.1.0` against pyproject's `0.3.0`. The README's "Quality
Pipeline" section describes relevance *scoring*, cross-source dedup, and
salary normalization across periods — none of which exist. `research/` documents
the Bundesagentur **v4** endpoint, which was retired server-side (see §4).

### F13 — Weak tests worth strengthening (Phase 0) — RESOLVED

Most tests are real, but: `test_get_salary_stats` asserts `average is not None`
and `min <= max` rather than the actual computed values — it would pass against
almost any implementation. `test_add_listing` / `test_add_listings` test list
`.append`. There is no test for `run_job_research`, none for report *content*,
and none for `_parse_salary_range` against realistic German salary strings.

---

## 4. Bundesagentur für Arbeit — porting from `mhp-bd-intelligence`

There is no BA integration today. `arbeitsagentur.de` appears only as a
web-search domain for the Claude backend, with a placeholder pattern matching any
path on the domain.

The sibling repo `mhp-bd-intelligence` has a working client at
`src/bd_signal_monitor/talent/jobsuche.py`. Directly reusable:

- **Endpoint:** `https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs`
- **Auth:** static public header `X-API-Key: jobboerse-jobsuche`, no registration.
- **v4 is dead.** BA retired `pc/v4` server-side on 2026-08-04; every query 404'd.
  Our `research/` docs still describe v4. Version drift is a *live* risk — keep
  `base_url` injectable and the response parser tolerant of both shapes, as the
  MHP client does in `posting_titles()`.
- **`veroeffentlichtseit`** (0–100 days) gives "posted in the last N days" — a
  capability this project currently has in no backend.
- **Gotcha:** on a zero-result query the employer facet does *not* come back
  empty; it falls back to a global top-employers histogram. Guard on
  `maxErgebnisse > 0` before trusting facet data.

**Not reusable:** MHP consumes only the aggregate employer facet. We need the
posting list itself (`ergebnisliste` → `stellenangebotsTitel`, `arbeitgeber`,
`arbeitsort`, `refnr` for the detail URL). Take the client and the operational
knowledge; write our own consumer.

**Terms of use.** The endpoint is reverse-engineered rather than official. BA's
portal terms §2a(3) restrict automated read-out "for the purpose of data
collection and evaluation", and §6b restricts reuse of postings. MHP recorded an
explicit risk acceptance in its ADR-016. Our posture is decided and recorded in
[decisions/001-bundesagentur-terms-of-use.md](decisions/001-bundesagentur-terms-of-use.md):
**opt-in, off by default, documented.**

Two further patterns worth borrowing from that repo: the
`sources/{base,catalog}.py` registry (precisely the abstraction Phase 3 needs)
and the `docs/decisions/` ADR practice (started here with ADR-001).

---

## 5. Target architecture

```
src/job_research/
  models.py          ← JobListing (+ job_id, source, source_id, posted_date: date|None, status)
  config.py          ← Config; board booleans replaced by an enabled-source set
  sources/
    base.py          ← JobSource protocol: fetch(params) -> list[JobListing]
    catalog.py       ← registry: id, label, backend, url pattern, default-enabled
    claude_search.py ← today's scraper.py
    jobspy_source.py ← today's jobspy_scraper.py
    bundesagentur.py ← new (Phase 4)
  pipeline/
    relevance.py     ← scored matching + negative keywords
    dedup.py         ← ONE cross-source implementation
    filters.py       ← salary, seniority, work type, posted-since
    interleave.py    ← round-robin + truncation
  store.py           ← SQLite job store: first_seen, last_seen, status
  analyzer.py        ← reporting only (csv module)
  utils.py
src/ui/app.py        ← per-request params; no module-level mutation
```

The key move: **scrapers fetch and map, the pipeline decides.** Every backend
gets the same quality treatment for free, and `hasattr` duck-typing disappears.

---

## 6. Phased plan

Each phase is one branch, merged fast-forward, with a changelog entry.

### Phase 0 — Guardrails · *small* — **DONE**

Refactoring without a gate is refactoring blind. Nothing else starts until this
lands.

- GitHub Actions workflow: `ruff check`, `mypy src/`, `pytest`.
- Fix the 8 existing mypy errors (F9). Add `pandas-stubs` to the dev group.
- Single-source the version via `importlib.metadata` (F12).
- Strengthen the weak assertions in `test_analyzer.py` to exact values (F13).
- **Characterization tests before the merge:** pin the current behaviour of both
  dedup implementations and of report generation, so Phase 2's merge is provably
  intentional rather than accidental.

### Phase 1 — Honesty pass · *small, high value* — **DONE**

Make the tool do what its UI claims. Independently useful even if later phases
slip.

- Implement salary and seniority as post-fetch filters (F1). Seniority derives
  from title tokens plus, where available, description.
- Remove salary/seniority from the cache key — once they are post-filters, the
  same fetch serves every threshold. This is a **significant** latency and cost
  win on repeated searches.
- Cache the full normalized fetch, not the truncated view (F6).
- Per-request `JobSearchParams`; drop module-level mutation (F4).
- Replace hand-rolled CSV with the `csv` module (F8).
- Correct the README and Info tab to describe what exists (F12).

### Phase 2 — Pipeline extraction · *medium* — **DONE**

- Introduce `pipeline/`; move dedup, relevance, interleave, and truncation out of
  both scrapers (F5).
- **One** dedup implementation, explicitly specified: URL match, then normalized
  title+company+location.
- Rewrite relevance as a score with a threshold and negative keywords (F3).
- Salary parsing gains unit and period detection; monthly and hourly figures
  normalize to annual, or stay `None` rather than guessing (F7).
- Scrapers reduce to a single-method Protocol; `max_jobs` and `total_found`
  become pipeline concerns, ending the per-backend divergence (F10).

### Phase 3 — Source registry · *medium*

- `sources/catalog.py` replaces the seven `JobBoardConfig` booleans with a
  registry keyed by source id; config carries `enabled_sources: set[str]`.
- Each entry declares: id, display label, serving backend, listing-URL pattern,
  default-enabled, and any opt-in caveat.
- `boards.py` adapters fold into the registry.
- The jobspy source derives `site_name` from enabled sources instead of the
  hardcoded list (F2).
- `Config.to_dict` generated from fields rather than hand-maintained — it is
  already missing `scraper_backend`, `claude_model`, `max_jobs_per_search`, and
  `interleave_sites`.

### Phase 4 — Bundesagentur source · *medium*

- Port the client: v6 base URL, static header, injectable `base_url`,
  shape-tolerant parser.
- Map `ergebnisliste` entries to `JobListing`; construct detail URLs from `refnr`.
- Wire `veroeffentlichtseit` to a new "posted within N days" filter — available
  to every backend that can express it.
- **Off by default**, opt-in via the registry, with the caveat surfaced in the UI
  and README per ADR-001.
- Tests run against recorded JSON fixtures; no live HTTP in the suite. A separate
  `scripts/probe_bundesagentur.py` handles manual calibration.

### Phase 5a — Seen-state store · *medium; the payoff*

Everything here is needed no matter where triage eventually happens.

- `JobListing` gains `job_id` (stable id: normalized source URL, else
  source+`source_id`, else normalized company+title+location), `source`,
  `first_seen`, `last_seen`.
- `posted_date` becomes `date | None` with per-source parsing.
- `store.py`: SQLite at `data/jobs.db` — stdlib, no new dependency, and it
  survives concurrent reads better than a JSON file.
- Run diff: **new** / still open / disappeared since the previous run.
- UI: "New since last run" as the default view.

**`job_id` must be human-tolerable, not a raw hash.** It is the one decision here
that is expensive to reverse: if jobs later become files in a vault (see 5b), the
id becomes the filename. Prefer a readable slug with a short hash suffix —
`ai-engineer-siemens-berlin-a3f2c1` — over a bare digest.

### Phase 5b — Triage destination · *deferred; decide after 5a runs for a while*

Where a job's *status* lives (interested / applied / rejected) is undecided, and
5a is deliberately built so it can stay that way. Three viable answers:

1. **In-app triage.** `status` column in the store, buttons in the Gradio UI,
   dismissed jobs suppressed from later runs. Self-contained; means living in the
   Gradio UI to do the triage.
2. **Obsidian (or any Markdown vault) as the destination.** Each new job is
   written as a note with YAML frontmatter (`company`, `location`, `salary`,
   `posted`, `source_url`, `status: new`). Triage happens by editing frontmatter
   in Obsidian; the tool reads it back on the next run to suppress what you have
   already rejected. Dataview then gives you boards and queries for free, and
   application notes live next to the job they belong to.
3. **Export only, no status.** Write new jobs out, track nothing but `first_seen`,
   and triage wherever you like with no round-trip.

Option 2 inverts the design pleasantly: the vault becomes the system of record
for *your* judgement, the SQLite store stays the system of record for *what the
boards said and when*. Neither has to know much about the other — the seam is
`job_id`.

**Do not decide this now.** Run 5a for a few weeks and see whether you actually
want triage inside the tool. The cost of deferring is one interface
(`Destination.write(new_jobs)` / `read_statuses()`), and 5a is not blocked on it.

### Phase 6 — Multi-backend orchestration · *medium*

- Run all enabled sources concurrently and merge through one pipeline.
- Cross-source dedup becomes load-bearing here: the same job appears on Indeed,
  LinkedIn, and BA simultaneously. A merged listing retains every source URL as
  provenance rather than discarding all but one.
- Per-source health reporting in the UI, so a silently failing source is visible
  rather than looking like "no results".

---

## 7. Standing risks

| Risk | Note |
|---|---|
| BA endpoint is unofficial | v4 was retired without notice. Keep the client swappable and fail soft; see ADR-001. |
| jobspy tracks site structure | Breakage is a matter of when. Phase 6's per-source health reporting makes it visible instead of silent. |
| Claude backend costs per search | Phase 1's cache-key fix removes the largest source of pointless re-fetches. |
| Sector skew | BA is dense for Mittelstand, public sector, and industrials; sparse for digital-native firms. Absence of a BA hit is not evidence of no hiring. |

---

## 8. Recommended order

Phase 0 → 1 deliver visible improvement within a small change budget and are
worth doing regardless of what follows. Phase 2 is the structural unlock — every
later phase is materially cheaper once the pipeline exists. Phase 5a is the reason
the project exists as a *tool* rather than a script, but it depends on the stable
identity that Phase 2's unified dedup establishes.

Phase 5b is deliberately open. Build 5a, live with it for a few weeks, and let
actual use decide whether triage belongs in the app, in a Markdown vault, or
nowhere. Nothing upstream is blocked on that answer.
