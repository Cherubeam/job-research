# ADR-001: Bundesagentur für Arbeit Jobsuche — access posture

## Status

Accepted — 2026-08-25. **Amended the same day**: constraint 1 (off by default)
was reversed by the risk owner once the integration was working. See
[Amendment](#amendment-2026-08-25--enabled-by-default) at the end. All other
constraints stand.

## Context

The Bundesagentur für Arbeit (BA) operates Germany's federal job board, the
largest single corpus of German job postings (1.5M+ listings). It is the highest
value-per-effort source available to this project: free, no registration, no
Cloudflare blocking, and it carries a `veroeffentlichtseit` parameter that gives
us "posted in the last N days" — a capability no current backend has.

A working client already exists in the sibling project `mhp-bd-intelligence`
(`src/bd_signal_monitor/talent/jobsuche.py`), along with spike findings and a
terms-of-use analysis (its ADR-016). The technical path is short.

The complication is access legitimacy. From MHP's verification of BA's published
terms:

1. **There is no official, sanctioned API.** The endpoint is reverse-engineered
   and documented by the community `bundesAPI` project. The
   `X-API-Key: jobboerse-jobsuche` value is a client id lifted from BA's own
   mobile app, not a key issued to us. BA has publicly regarded the open
   documentation of this interface as problematic, while never having contacted
   the operators or taken legal action.
2. **The portal terms restrict automated read-out.** §2a(3) prohibits "robots,
   web spiders or similar technologies" and states it is not permitted to read
   out portal content "for the purpose of data collection and evaluation".
   §6b limits reuse of posted offers to BA and its selected cooperation partners.
3. **The endpoint is unstable.** BA retired the `pc/v4` path server-side on
   2026-08-04 with no notice; every query began returning 404.

Two things distinguish our situation from MHP's, and they cut in opposite
directions:

- **Lower exposure.** `mhp-bd-intelligence` is a commercial internal tool
  building a derived dataset across tracked accounts. This project is a personal
  job-search aid: a job seeker reading job advertisements at low volume, which is
  materially closer to the portal's intended use than bulk collection for
  evaluation.
- **Higher visibility.** This repository is public under the MIT license.
  Whatever we ship, others may run at volumes and for purposes we do not control.

## Decision

**Integrate BA as an opt-in source, disabled by default, with the caveat
documented where a user will actually see it.**

Binding constraints:

1. ~~**Off by default.** The source registry entry ships disabled. Enabling it is
   a deliberate act by the person running the tool.~~ *(Reversed — see the
   amendment below. The caveat still renders next to the source in the UI.)*
2. **No bulk enumeration.** The client fetches a bounded result page for an
   explicit user-initiated search. No crawling of the full board, no scheduled
   sweeps, no pagination-to-exhaustion.
3. **Caveat surfaced, not buried.** A short note in the README and in the UI
   next to the toggle: unofficial endpoint, terms restrict automated read-out,
   enable at your own discretion. Link to this ADR.
4. **Personal use framing.** The README does not present BA as a data-collection
   feature or market-analysis substrate; it is one more place to look for jobs
   you might apply to.
5. **Swappable by construction.** The source implements the same `JobSource`
   protocol as every other backend, with an injectable `base_url`. If BA rotates
   the key, changes the shape again, or the posture has to change, replacing it
   costs one module.

## Alternatives considered

**Ship it enabled by default, like any other board.** Rejected. Defensible for a
single person's own use, but this is a public repository — a default-on
unsanctioned scraper is a decision made silently on behalf of every future user.
Opt-in costs one checkbox and makes the choice explicit.

**Skip BA; use a sanctioned alternative such as Adzuna.** Deferred, not rejected.
Adzuna has documented terms and a free tier, but a smaller and differently-shaped
German corpus. Worth adding later as a complement. It is not a reason to forgo
the largest German job corpus for personal search use in the meantime.

**Scrape the BA portal HTML instead of the endpoint.** Rejected — strictly worse.
§2a(3)'s robots prohibition targets exactly that, and it forfeits clean
structured data.

## Consequences

**Easier:**
- The largest German job corpus becomes available, along with recency filtering
  that benefits every other source once the filter exists.
- The posture is explicit and citable rather than an unexamined default.

**Harder:**
- One more toggle, and a caveat to explain in the README.
- BA's instability (see the v4 retirement) means this source will break without
  warning at some point. The `JobSource` protocol and injectable `base_url` keep
  the blast radius to a single module, and per-source health reporting
  (architecture review, Phase 6) makes the failure visible rather than silent.

**Watch:**
- If BA publishes a genuine open-data offering, migrate to it immediately.
- If this project ever grows a scheduled/unattended mode, revisit this ADR before
  pointing it at BA — recurring automated fetches are a different posture than
  user-initiated search.

## References

- Architecture review, §4 — [../architecture-review.md](../architecture-review.md)
- `mhp-bd-intelligence`: `docs/decisions/016-bundesagentur-terms-of-use.md`,
  `docs/jobsuche-spike-findings-2026-06-22.md`
- BA terms of use: https://www.arbeitsagentur.de/en/terms-of-use
- Community API documentation: https://jobsuche.api.bund.dev/


## Amendment (2026-08-25) — enabled by default

**Change:** `arbeitsagentur` ships with `default_enabled=True`, alongside Indeed.
Constraints 2–5 (no bulk enumeration, caveat surfaced, personal-use framing,
swappable by construction) are unchanged and still enforced by tests.

**Why:** the risk owner decided that for this tool's actual use — one person
searching for jobs to apply to, at a handful of queries a day — the federal job
board is the single most useful German source, and requiring an opt-in for it
made the default configuration worse without meaningfully changing the exposure.
The `MAX_PAGES` ceiling and the absence of any scheduled path already bound the
volume far below anything resembling data collection.

**What this does not change:** the endpoint is still unofficial, BA's terms still
restrict automated read-out, and the caveat still renders next to the source in
the UI so the person running it sees the situation. The original reasoning for
opt-in — that this is a public repository and others may run it at volumes we do
not control — remains true and is recorded here rather than deleted. Anyone
forking this should make their own call; `ENABLED_SOURCES` is how you make it.

**Revisit if:** the project grows an unattended or scheduled mode, at which point
recurring automated fetches become a different posture than user-initiated
search, and this decision should be re-taken rather than inherited.
