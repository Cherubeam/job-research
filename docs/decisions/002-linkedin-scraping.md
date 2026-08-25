# ADR-002: LinkedIn — scraping posture

## Status

Accepted — 2026-08-25. LinkedIn is opt-in and disabled by default.

## Context

The jobspy backend has scraped LinkedIn since v0.3.0, where `site_name` was
hardcoded to `["linkedin", "indeed"]` with no way to turn it off. Phase 3 made
sources selectable and, in unifying the two backends' defaults, also switched the
Claude backend from Indeed-only to Indeed **and** LinkedIn. That second change
was made for consistency without examining what LinkedIn access actually costs.

Three things argue against LinkedIn being on by default.

**1. The project's own research already concluded this.**
`research/JOB_BOARDS_RESEARCH_INDEX.md` answers "Can I scrape Indeed or
LinkedIn?" with "**No.** Both explicitly prohibit scraping in their ToS, have
strong anti-bot measures, and may pursue legal action."
`research/German_Job_Boards_API_Analysis.md` rates LinkedIn scraping "Very Hard"
and recommends "Do NOT scrape". That conclusion was reached before the scraper
was written and then never applied to it.

**2. LinkedIn's terms prohibit automated collection**, and its Jobs API is
partner-only with enterprise pricing — there is no sanctioned free path for a
personal tool. (This ADR does not attempt to summarise LinkedIn's current
enforcement posture; the prohibition itself is not in dispute.)

**3. It half-works, which is worse than failing.** From python-jobspy's
implementation as installed:

- It calls the unauthenticated guest endpoint
  `/jobs-guest/jobs/api/seeMoreJobPostings/search` with a spoofed Chrome
  user-agent and 3–7s randomized delays between pages.
- On HTTP 429 it logs `"Blocked by LinkedIn for too many requests"` and
  **returns the results collected so far**. A block is therefore
  indistinguishable, from the caller's side, from a search that genuinely had
  few matches.
- `linkedin_fetch_description=True` — which this project set — issues one
  additional request per job to `/jobs/view/{id}`. That code path explicitly
  gives up when LinkedIn redirects to `linkedin.com/signup`, i.e. the auth wall.
  So the extra request volume, and the extra block risk, is spent on
  descriptions that frequently never arrive.

The counter-argument is real: LinkedIn carries job postings that appear nowhere
else, particularly at digital-native employers — exactly the segment where the
Bundesagentur corpus is weakest (see ADR-001). Removing it entirely would leave
a coverage hole.

## Decision

**LinkedIn stays available but is opt-in and off by default**, and the
per-job description fetch is disabled.

1. `default_enabled=False` in the source registry, with a caveat string, so it
   renders flagged in the UI and requires deliberate selection.
2. `linkedin_fetch_description=False`. It doubles request volume for data the
   auth wall usually withholds — a bad trade at any default.
3. The Claude backend returns to **Indeed-only** by default, restoring the
   deliberate v0.2.0 choice that Phase 3 overrode without justification.
4. Indeed is consequently the only default-on source.

Enabling LinkedIn is a decision the person running the tool makes, with the
caveat in front of them.

## Alternatives considered

**Remove LinkedIn entirely.** Rejected. The coverage it provides is real and the
choice is legitimately the operator's — a personal job seeker reading job
adverts at low volume is a different proposition from bulk collection. Removing
it would also not stop anyone, just make them patch the registry.

**Leave it on and only fix the description fetch.** Rejected. That addresses the
wasted requests but still makes an unsanctioned, silently-degrading source the
default for a public repository, against the project's own research.

**Keep it on for the Claude backend only**, since `web_search` with
`allowed_domains` is a search index rather than direct scraping. Rejected as too
subtle a distinction to encode in a checkbox: the same source id would mean
"indexed" or "scraped" depending on an unrelated setting. If that distinction
becomes worth drawing, it belongs in the registry as separate entries.

## Consequences

**Easier:**
- The default configuration no longer scrapes a source that prohibits it.
- Fewer requests per search, and no silent partial results from a rate-limit
  block in the default path.
- The reasoning is recorded, so the default does not quietly drift back.

**Harder:**
- Out of the box the tool searches one board. Coverage now depends on the user
  opting into more, or on the Bundesagentur source (ADR-001) landing.
- Descriptions from LinkedIn are unavailable even when it is enabled. If they
  turn out to matter, re-enabling the fetch is one flag — but measure the block
  rate first.

**Watch:**
- If a sanctioned path appears (an affordable Jobs API tier, or an aggregator
  that licenses LinkedIn postings), prefer it and revisit this ADR.
- If `interleave` and cross-source dedup go untested in practice because only one
  source is on by default, keep exercising them via the test suite rather than
  assuming real runs cover them.

## References

- Architecture review — [../architecture-review.md](../architecture-review.md)
- ADR-001 (Bundesagentur posture) — [001-bundesagentur-terms-of-use.md](001-bundesagentur-terms-of-use.md)
- `research/JOB_BOARDS_RESEARCH_INDEX.md`, `research/German_Job_Boards_API_Analysis.md`
