# ADR-003: Google Jobs — access posture

## Status

Accepted — 2026-08-25. Available, opt-in, disabled by default.

## Context

Google Jobs is an aggregator: it surfaces postings from boards this tool does
not reach directly, including company career pages and boards with no API. That
is a different kind of coverage from adding one more board — it widens the net
rather than deepening one corner of it. python-jobspy supports it, and unlike
Indeed or LinkedIn it needs no per-site handling: jobspy composes the query from
`search_term` and `location` itself.

Two things about it were initially assessed wrongly and are corrected here.

**1. It is not free of terms considerations.** Reading jobspy's implementation:
it issues `GET https://www.google.com/search` with `udm=8`, scrapes the returned
HTML for an async cursor, then pages through an internal callback endpoint
(`/async/callback:550`) parsing an undocumented nested-array payload. That is
automated querying of Google Search and parsing of its result pages, which
Google's terms restrict. It was described as "the clean addition without a terms
problem" before the code was read; that was wrong.

**2. It needs no `google_search_term` plumbing.** `google_search_term` is an
*override* that replaces the entire composed query. Setting it would discard the
location clause jobspy appends. Leaving it unset is both simpler and better.

How it differs from LinkedIn (ADR-002) is worth stating precisely, because the
difference is real but narrower than it first appears:

- **No authentication wall.** The results are public search results, not content
  behind a login. Nothing is being accessed that a browser would not show.
- **No per-account exposure.** There is no account to suspend, unlike a LinkedIn
  profile scraping its own employer's board.
- **But the same fragility.** It parses an undocumented internal endpoint, so it
  will break without notice, and it depends on Google not serving a bot check.

The interface is also structurally unstable in a way the others are not: the
`/async/callback:550` payload is positional, untyped, and entirely internal.

## Decision

**Ship Google Jobs as an opt-in source, disabled by default**, with a caveat
rendered next to it in the UI — the same treatment as LinkedIn and, before the
amendment, the Bundesagentur.

1. `default_enabled=False` in the source registry, with a caveat naming this ADR.
2. No `google_search_term`; jobspy's composed query is used as-is.
3. `job_url_pattern` is deliberately permissive. Google Jobs links out to the
   *original* posting — a company site, LinkedIn, anywhere — so there is no
   domain to recognise. The pattern is only consulted by the Claude backend's
   URL validation, and Google is not reachable that way.

A useful side effect of (3): because Google returns the original posting URL,
its results deduplicate naturally against Indeed and the Bundesagentur when the
same job is found twice, and the survivor keeps both links.

## Alternatives considered

**On by default, as the coverage argument suggests.** Rejected. The coverage is
genuinely attractive, but this is a public repository and the default
configuration should not automatically query a service whose terms restrict it.
The same reasoning as ADR-002; the Bundesagentur amendment turned on the risk
owner's explicit decision, not on the coverage being valuable.

**Skip it and add Glassdoor instead.** Rejected for now — Glassdoor is rated
"do not scrape" in the project's own research (Cloudflare, login walls) and
would need the same ADR plus worse odds of working. Google Jobs reaches more
boards for less trouble.

**Reach Google Jobs through the Claude backend instead.** Rejected: Claude's web
search over `google.com` would return search-results pages, not job listings —
exactly the search/category-page problem the URL validation exists to reject.

## Consequences

**Easier:**
- Access to postings from boards this tool has no other route to.
- Recency filtering now narrows the *fetch* for every jobspy source
  (`hours_old`), not just the Bundesagentur, since Google honours it in-query.

**Harder:**
- One more source that will break without warning. It parses an undocumented
  internal endpoint; when Google changes it, jobspy has to catch up.
- Per-source health reporting (Phase 6) matters more here than anywhere else:
  a silent Google failure would otherwise look like a quiet market.

**Watch:**
- If Google starts serving bot checks to this traffic, results will thin out
  rather than error. Compare the per-source counts across runs.
- If a sanctioned aggregator appears (Adzuna is already tracked in ADR-001 as
  the migration candidate for the Bundesagentur), prefer it.

## References

- ADR-001 (Bundesagentur posture) — [001-bundesagentur-terms-of-use.md](001-bundesagentur-terms-of-use.md)
- ADR-002 (LinkedIn posture) — [002-linkedin-scraping.md](002-linkedin-scraping.md)
- `research/German_Job_Boards_API_Analysis.md` — anti-scraping assessments
