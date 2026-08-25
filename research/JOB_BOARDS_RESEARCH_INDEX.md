# German Job Boards Research - Document Index

**Research Completed:** November 20, 2025
**Total Documents:** 4 research documents created

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

## What was actually built (2026-08-25)

The recommendations in these documents have been acted on. Current state:

| Recommendation | Outcome |
|---|---|
| Implement the Arbeitsagentur API first | Done — `SCRAPER_BACKEND=bundesagentur`, on by default. v6 endpoint, structured salary, server-side recency filter. |
| Do not scrape Indeed or LinkedIn | Partially followed. Indeed is scraped via python-jobspy (default on); LinkedIn is available but **off by default** per [ADR-002](../docs/decisions/002-linkedin-scraping.md). |
| Evaluate the LinkedIn API | Not pursued — partner-only, enterprise pricing, no viable tier for a personal tool. |
| Add XING | Dropped — the domain blocks Anthropic's web crawler. |
| Monster RSS feeds | Not implemented. Monster remains reachable only via the Claude web-search backend. |
| Adzuna as a sanctioned alternative | Still open — noted in [ADR-001](../docs/decisions/001-bundesagentur-terms-of-use.md) as the migration target if the BA posture has to change. |

---

## Quick Navigation

### For Implementation Teams
**Start Here:** `QUICK_REFERENCE_API_COMPARISON.md`
- One-page decision matrix
- Implementation timeline
- Cost estimates
- Quick start guides

**Then Read:** `German_Job_Boards_API_Analysis.md`
- Detailed platform analysis
- Technical specifications
- Legal considerations
- Best practices

### For Business Stakeholders
**Start Here:** `QUICK_REFERENCE_API_COMPARISON.md` (Executive Summary section)
- Market coverage strategies
- Cost-benefit analysis
- Risk assessment

**Optional:** `German_Job_Boards_API_Analysis.md` (Comparison Tables section)
- Detailed comparison tables
- Market position data

### For Researchers & Developers
**Technical Analysis:** `German_Job_Boards_API_Analysis.md`
- Complete platform analysis (10 platforms)
- API documentation quality
- Anti-bot measures
- Data field specifications

**Sources & References:** `API_RESEARCH_SOURCES.md`
- All research sources
- Verification guidelines
- Community resources

### For General Understanding
**Platform Overview:** `German_Job_Boards.md` (existing document)
- Overview of German job market
- Platform descriptions
- Industry-specific boards
- Job search tips

---

## Document Descriptions

### 1. German_Job_Boards_API_Analysis.md (30KB)
**Purpose:** Comprehensive technical analysis of API availability and web scraping feasibility

**Contents:**
- Executive Summary
- Detailed analysis of 10 major platforms:
  - StepStone
  - Indeed Germany
  - LinkedIn
  - Xing
  - Monster Germany
  - Glassdoor Germany
  - Arbeitsagentur (Federal Employment Agency)
  - Jobware
  - CareerBuilder Germany
  - Dice
- Comparison tables (API availability, market position, scraping difficulty)
- Implementation recommendations
- Legal & compliance considerations
- GDPR guidance
- Cost-benefit analysis

**Best For:**
- Technical leads planning implementation
- Developers evaluating options
- Legal teams assessing compliance
- Project managers estimating resources

---

### 2. QUICK_REFERENCE_API_COMPARISON.md (15KB)
**Purpose:** One-page quick reference for rapid decision-making

**Contents:**
- At-a-glance decision matrix
- The 80/20 solution (fastest path to 80% coverage)
- Quick implementation guides with code samples
- Technical decision tree
- Cost estimates by tier
- Market coverage strategies
- Red flags and what to avoid
- GDPR compliance checklist
- Testing & validation checklist

**Best For:**
- Quick reference during meetings
- Initial project scoping
- Budget planning
- Timeline estimation
- Developer quick-start

---

### 3. API_RESEARCH_SOURCES.md (21KB)
**Purpose:** Complete documentation of research methodology and sources

**Contents:**
- Research methodology
- Sources organized by platform (100+ links)
- Official API documentation links
- Market share data sources
- Anti-bot research sources
- Legal and compliance resources
- Research limitations
- Verification recommendations
- Update schedule

**Best For:**
- Verifying research findings
- Conducting further research
- Academic citations
- Due diligence
- Fact-checking

---

### 4. German_Job_Boards.md (5.5KB) [Existing Document]
**Purpose:** General overview of German job board landscape

**Contents:**
- Overview of German job market (1,000+ portals, 77M monthly ads)
- Top general job boards (StepStone, Indeed, Xing, LinkedIn, Arbeitsagentur)
- Specialized platforms by industry
- Government resources
- Job search tips
- Sector-specific recommendations

**Best For:**
- Understanding the German job market
- Identifying relevant platforms
- Job seekers
- Market overview for stakeholders

---

## Key Findings Summary

### Top Recommendations

**Best Free Option:**
- **Arbeitsagentur API** - 1.5M+ jobs, free, 1,000 req/hour
- **Monster RSS** - Supplementary data, easy implementation

**Best Paid Options:**
- **Indeed API** - #1 market position, excellent docs, partnership required
- **StepStone API** - #2 in Germany, 39.4% market share, partnership required

**Best for Professional Networks:**
- **Xing** - DACH leader (19M members), third-party APIs available
- **LinkedIn** - Global leader, expensive enterprise API

### Platforms to Avoid

**Dice:**
- Closed German operations in 2018
- Minimal German job listings
- Not relevant for German market

**Glassdoor (for API):**
- Public API shut down in 2021
- Extremely difficult to scrape
- Partner-only access

**Web Scraping (Generally):**
- Indeed - Explicitly prohibited, strong anti-bot
- LinkedIn - Legal action risk, very expensive alternative
- StepStone - Strong protection, API available instead

---

## Implementation Roadmap

### Phase 1: Proof of Concept (Week 1)
**Documents to Read:**
- `QUICK_REFERENCE_API_COMPARISON.md` - Quick implementation guide
- `German_Job_Boards_API_Analysis.md` - Arbeitsagentur section

**Action Items:**
1. Implement Arbeitsagentur API
2. Test data quality
3. Validate GDPR compliance
4. Estimate coverage

**Expected Coverage:** 40-50% of market

---

### Phase 2: MVP (Month 1)
**Documents to Read:**
- `QUICK_REFERENCE_API_COMPARISON.md` - Free tier strategy
- `German_Job_Boards_API_Analysis.md` - Monster section

**Action Items:**
1. Add Monster RSS feeds
2. Implement deduplication
3. Build data normalization
4. Set up monitoring

**Expected Coverage:** 60-70% of market

---

### Phase 3: Commercial Launch (Months 2-3)
**Documents to Read:**
- `German_Job_Boards_API_Analysis.md` - Indeed & StepStone sections
- `QUICK_REFERENCE_API_COMPARISON.md` - Business tier strategy
- `API_RESEARCH_SOURCES.md` - Partnership contacts

**Action Items:**
1. Apply for Indeed partnership
2. Apply for StepStone partnership
3. Implement Indeed API
4. Implement StepStone API
5. Legal review of ToS compliance

**Expected Coverage:** 85-90% of market

---

### Phase 4: Enterprise Features (Months 4-6)
**Documents to Read:**
- `German_Job_Boards_API_Analysis.md` - LinkedIn & Xing sections
- `QUICK_REFERENCE_API_COMPARISON.md` - Enterprise tier

**Action Items:**
1. Evaluate LinkedIn API (if budget allows)
2. Implement Xing third-party API
3. Add CareerBuilder for EU hosting
4. Enhance data quality
5. Add company review data (if Glassdoor access obtained)

**Expected Coverage:** 95%+ of market

---

## Cost Summary by Phase

### Phase 1: POC
- **Cost:** $0/month
- **Platforms:** Arbeitsagentur
- **Coverage:** 40-50%

### Phase 2: MVP
- **Cost:** $0/month
- **Platforms:** Arbeitsagentur + Monster RSS
- **Coverage:** 60-70%

### Phase 3: Commercial
- **Cost:** $500-2,000/month (estimate)
- **Platforms:** Above + Indeed + StepStone
- **Coverage:** 85-90%

### Phase 4: Enterprise
- **Cost:** $2,000-10,000/month (estimate)
- **Platforms:** Above + LinkedIn + Xing + CareerBuilder
- **Coverage:** 95%+

---

## Technical Requirements by Phase

### Phase 1-2: Simple Stack
```
Python 3.11+
requests / httpx
PostgreSQL
Basic cron jobs
```

### Phase 3: Production Stack
```
Python FastAPI
Celery + Redis
PostgreSQL
OAuth 2.0 implementation
Monitoring (Prometheus/Grafana)
```

### Phase 4: Enterprise Stack
```
Microservices architecture
Kafka or RabbitMQ
Elasticsearch
Redis caching
Load balancing
Kubernetes (optional)
```

---

## Legal & Compliance Checklist

Before implementation, review:

**Legal Documents:**
- [ ] Each platform's Terms of Service
- [ ] robots.txt files
- [ ] GDPR compliance requirements
- [ ] Data processing agreements
- [ ] Privacy policy requirements

**Technical Compliance:**
- [ ] Rate limiting implementation
- [ ] Error handling and retry logic
- [ ] Data retention policies
- [ ] Security measures (encryption, access control)
- [ ] Logging and audit trails

**Recommended Reading:**
- `German_Job_Boards_API_Analysis.md` - Legal & Compliance section
- `QUICK_REFERENCE_API_COMPARISON.md` - GDPR checklist
- `API_RESEARCH_SOURCES.md` - Legal resources

---

## Frequently Asked Questions

### Which document should I read first?
**Answer:** `QUICK_REFERENCE_API_COMPARISON.md` for a quick overview, then `German_Job_Boards_API_Analysis.md` for details.

### Can I scrape Indeed or LinkedIn?
**Answer:** No. Both explicitly prohibit scraping in their ToS, have strong anti-bot measures, and may pursue legal action. Use their official APIs instead.

### What's the fastest way to get German job data?
**Answer:** Implement the Arbeitsagentur API (free, 2 hours to set up, 1.5M+ jobs).

### What's the best free solution?
**Answer:** Arbeitsagentur API + Monster RSS feeds (covers ~60-70% of market, $0 cost).

### What's the most comprehensive solution?
**Answer:** Indeed + StepStone + Arbeitsagentur + LinkedIn + Xing (~95%+ coverage, $2,000-10,000/month estimate).

### Is web scraping legal in Germany?
**Answer:** German courts ruled it legal IF you don't circumvent technical measures and respect robots.txt. However, many platforms explicitly prohibit it in ToS. See `German_Job_Boards_API_Analysis.md` for details.

### How much does Indeed API cost?
**Answer:** Pricing not publicly disclosed. Contact Indeed partnership team. Industry estimates suggest $500-2,000/month for moderate usage, but varies by volume and use case.

### Which platforms have free APIs?
**Answer:** Arbeitsagentur (1,000 req/hour), Monster RSS (feed-based). All others require payment or partnerships.

### What about GDPR compliance?
**Answer:** Essential for any EU data processing. See GDPR checklist in `QUICK_REFERENCE_API_COMPARISON.md` and Legal section in `German_Job_Boards_API_Analysis.md`.

### How often should I update my data?
**Answer:**
- Real-time: Use API webhooks (if available)
- Hourly: High-priority job boards
- Every 4-6 hours: Most job boards (respects rate limits)
- Daily: Supplementary sources

---

## Update History

**Version 1.0 - November 20, 2025**
- Initial comprehensive research
- 10 platforms analyzed
- 100+ sources consulted
- Created 4 documents totaling 66KB of analysis

**Next Review Scheduled:** February 2026 (Quarterly)

**Continuous Monitoring:**
- Terms of Service changes
- API availability updates
- Market share shifts
- New platform launches

---

## Contact & Support

### For Research Updates
Check this document quarterly for updates to research findings.

### For Platform-Specific Questions
Refer to contact information in `German_Job_Boards_API_Analysis.md`

### For Implementation Questions
Review code examples in:
- `QUICK_REFERENCE_API_COMPARISON.md` (Quick start)
- GitHub repositories listed in `API_RESEARCH_SOURCES.md`

### For Legal Questions
Consult qualified legal counsel. This research is not legal advice.

---

## Document File Paths

All documents located in:
```
/Users/marcobraun/Documents/01 Projects/Software Projects/Job Research/
```

**Research Documents (New):**
- `German_Job_Boards_API_Analysis.md` (30KB)
- `QUICK_REFERENCE_API_COMPARISON.md` (15KB)
- `API_RESEARCH_SOURCES.md` (21KB)
- `JOB_BOARDS_RESEARCH_INDEX.md` (this file)

**Existing Documents:**
- `German_Job_Boards.md` (5.5KB)
- `README.md` (project overview)
- `PROJECT_STRUCTURE.md` (project structure)
- `SETUP.md` (setup instructions)

---

## Recommended Reading Order

### For Quick Start (30 minutes)
1. This index (5 min)
2. `QUICK_REFERENCE_API_COMPARISON.md` - At-a-glance section (10 min)
3. `QUICK_REFERENCE_API_COMPARISON.md` - Quick implementation guide (15 min)

### For Implementation (2 hours)
1. `QUICK_REFERENCE_API_COMPARISON.md` (full read - 30 min)
2. `German_Job_Boards_API_Analysis.md` - Relevant platform sections (1 hour)
3. `API_RESEARCH_SOURCES.md` - Official documentation links (30 min)

### For Comprehensive Understanding (4 hours)
1. `German_Job_Boards.md` - Market overview (30 min)
2. `QUICK_REFERENCE_API_COMPARISON.md` (45 min)
3. `German_Job_Boards_API_Analysis.md` (full read - 2 hours)
4. `API_RESEARCH_SOURCES.md` - Full review (45 min)

---

## Key Metrics Tracked

**Platform Coverage:**
- 10 major German job boards analyzed
- Market leaders: Indeed (#1), StepStone (#2), Monster (#3)
- Professional networks: LinkedIn, Xing
- Official: Arbeitsagentur (1.5M+ jobs)

**API Availability:**
- 4 platforms with official APIs (Arbeitsagentur, Indeed, StepStone, LinkedIn)
- 2 platforms with third-party APIs (Xing, CareerBuilder)
- 3 platforms with limited/no API (Monster RSS only, Glassdoor closed, Jobware unknown)
- 1 platform not recommended (Dice - closed German ops)

**Cost Range:**
- Free: Arbeitsagentur, Monster RSS
- Low ($0-500/month): Third-party Xing APIs
- Medium ($500-2,000/month): Indeed/StepStone partnerships (estimated)
- High ($2,000-10,000+/month): LinkedIn + comprehensive coverage

**Market Coverage:**
- Free options: 60-70% coverage
- Business tier: 85-90% coverage
- Enterprise tier: 95%+ coverage

---

## Success Criteria

Your implementation should aim for:

**Data Quality:**
- [ ] 95%+ accuracy in job listings
- [ ] < 5% duplicate rate
- [ ] < 24 hour data freshness
- [ ] Complete required fields (title, company, location, description)

**Technical Performance:**
- [ ] 99.5%+ uptime
- [ ] < 2 second response time
- [ ] Proper error handling
- [ ] Rate limit compliance (0 violations)

**Legal Compliance:**
- [ ] 100% ToS compliance
- [ ] GDPR requirements met
- [ ] robots.txt respected
- [ ] Privacy policy published
- [ ] Legal review completed

**Business Metrics:**
- [ ] Target market coverage achieved
- [ ] Within budget constraints
- [ ] User satisfaction > 4/5
- [ ] Cost per job listing optimized

---

## Version Information

**Document Version:** 1.0
**Created:** November 20, 2025
**Last Updated:** November 20, 2025
**Next Review:** February 2026
**Research Valid Until:** August 2026 (estimate - verify platforms regularly)

---

**End of Index**

For questions, updates, or corrections, please review the source documents or conduct updated research as market conditions change.
