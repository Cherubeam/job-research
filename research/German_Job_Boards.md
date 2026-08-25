# German Job Boards & Platforms

A comprehensive guide to the most important job boards and platforms for finding work in Germany.

## Overview

Germany hosts over 1,000 job portals publishing approximately 77 million job advertisements monthly. The job market is diverse with general platforms, specialized boards, and professional networks serving different industries and career stages.

---

> **Status note (2026-08-25).** This document records research completed in
> November 2025. Parts of it have since been superseded by what was actually
> built and verified against live endpoints. In particular:
>
> - **The Bundesagentur endpoint is now `pc/v6`, not `pc/v4`.** BA retired v4
>   server-side on 2026-08-04 and every v4 query 404s. The v4 URLs below have
>   been corrected in place.
> - **The response shape is not what the docs implied.** Postings use `firma`,
>   `stellenlokationen`, `referenznummer`, and `datumErsteVeroeffentlichung`,
>   and about a third carry structured pay (`gehaltsspanneVon`/`Bis`,
>   `festgehalt`, `verguetungsangabe`). Verified 2026-08-25 —
>   see `scripts/probe_bundesagentur.py`.
> - **XING was dropped** — its domain blocks Anthropic's web crawler.
> - **The "do not scrape LinkedIn" conclusion below still stands** and is now
>   recorded as [ADR-002](../docs/decisions/002-linkedin-scraping.md); the
>   Bundesagentur access posture is [ADR-001](../docs/decisions/001-bundesagentur-terms-of-use.md).
>
> For what the tool actually does today, read `README.md` and
> `docs/architecture-review.md` rather than the recommendations here.

---

## Top General Job Boards

### 1. **StepStone.de**
- **Website:** stepstone.de
- **Focus:** General job board covering all occupations, sectors, and regions
- **Scale:** 15 million monthly visits, 50,000+ active vacancies
- **Reach:** Used by 150,000+ companies
- **Best for:** Comprehensive job search across Germany

### 2. **Indeed.de**
- **Website:** indeed.de
- **Focus:** General job board with web crawler functionality
- **Advantage:** Aggregates jobs from company websites and other job boards
- **Best for:** Broader job discovery beyond traditional postings

### 3. **XING**
- **Website:** xing.com
- **Type:** Professional social network
- **Members:** 19 million across DACH region (Germany, Austria, Switzerland)
- **Best for:** Networking and professional development in German-speaking countries

### 4. **LinkedIn**
- **Website:** linkedin.com
- **Type:** Professional social network
- **Features:** Personalized job recommendations based on profile information
- **Best for:** International opportunities and professional branding

### 5. **Jobbörse.de**
- **Website:** arbeitsagentur.de/jobboerse
- **Type:** Federal Employment Agency job exchange
- **Scale:** 1.5 million+ job ads hosted
- **Coverage:** 6,000+ different professions
- **Best for:** Government-backed comprehensive job search

---

## Specialized Platforms by Industry

### Tech & Engineering
- **Honeypot.io** - Tech-focused jobs
- **Imagine Jobs** - Tech roles
- **Wellfound** - Startup and tech positions
- **Jobvector.de** - Engineers, physicists, scientists

### Students & Graduates
- **Staufenbiel.de** - Students and young professionals
- **Absolventa.de** - Graduate jobs
- **JobTeaser** - Entry-level positions

### Startups
- **Gründerszene.de** - German startup jobs
- **Germany Startup Jobs** - All startup opportunities
- **Berlin Startup Jobs** - Berlin-specific startups
- **AngelList (Wellfound)** - Early-stage companies
- **ArbeitNow.com** - Remote and startup roles

### Social & Sustainability
- **GoodJobs.eu** - Socially responsible positions
- **Idealist.org** - Non-profit and sustainability roles

### Creative Fields
- **DasAuge.de** - Creative industry jobs (design, advertising, etc.)

### Mid-Sized Companies (Mittelstand)
- **MittelstandsJob.de** - SME positions
- **MittelstandsKarriere.de** - SME career opportunities

### City-Specific Platforms
- **Talent Berlin** - Berlin job market
- **JoYo Hamburg** - Hamburg opportunities

---

## Government & Official Resources

### Bundesagentur für Arbeit (Federal Employment Agency)
- **Type:** Government-operated labor service
- **Services:** Job Exchange, ZAV (Central Agency for Foreign and Professional Affairs)
- **ZAV:** Specializes in supporting international applicants
- **Website:** arbeitsagentur.de

---

## Innovative/Alternative Platforms

### Truffls
- **Type:** Swipe-based job matching (similar to dating apps)
- **Features:** Smartphone-friendly interface
- **Best for:** Modern, casual job search approach

### Talentcube
- **Type:** Video-based candidate presentation
- **Features:** Personal video profiles showcase candidates
- **Best for:** Creative and modern industries

### JobNinja
- **Type:** AI-powered job portal
- **Features:** Uses artificial intelligence to distribute job advertisements
- **Traffic:** 2.2 million+ monthly website visits

---

## Tips for Success in the German Job Market

1. **Keep Profiles Updated**
   - LinkedIn and XING profiles should be current and complete
   - German employers value professional networking presence

2. **Timeline Expectations**
   - Recruitment and networking in Germany takes time
   - Plan for longer application processes

3. **Language Matters**
   - Learning German significantly enhances job opportunities
   - While English is spoken, German language skills are highly valued
   - Many positions require German language proficiency

4. **Networking**
   - Attend industry events and professional conferences
   - Build connections within your field
   - Use XING and LinkedIn for professional relationship building

5. **Apply Directly**
   - Don't rely solely on job boards
   - Visit company websites directly for open positions
   - Direct applications often receive more attention

---

## By Sector Summary

| Sector | Best Platforms |
|--------|----------------|
| **Tech** | Honeypot.io, Imagine Jobs, Jobvector.de |
| **Finance/Corporate** | StepStone, Indeed, LinkedIn, XING |
| **Startups** | Gründerszene, Wellfound, AngelList |
| **Education/Students** | Absolventa, Staufenbiel, JobTeaser |
| **Creative** | DasAuge.de, LinkedIn |
| **Public Sector** | Arbeitsagentur, regional government websites |
| **Sustainability/Social** | GoodJobs.eu, Idealist.org |
| **Remote Work** | ArbeitNow, Wellfound, Indeed |

---

## Additional Resources

- **German Ministry of Labor:** Provides information on work permits and employment regulations
- **Expatica:** Guides for expats working in Germany
- **Make it in Germany:** Official German government portal for skilled workers

---

**Last Updated:** November 2025

*Note: Job board popularity and availability can change. Always verify current website URLs and features when applying.*
