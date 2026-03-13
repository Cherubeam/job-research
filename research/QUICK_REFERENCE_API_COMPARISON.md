# Quick Reference: German Job Boards API Comparison

**Last Updated:** November 20, 2025

A one-page quick reference for technical decision-making.

---

## At-a-Glance Decision Matrix

```
┌─────────────────────┬──────────────┬──────────────┬──────────────┬──────────────┐
│ Platform            │ Best For     │ Access Type  │ Difficulty   │ Cost         │
├─────────────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ Arbeitsagentur ⭐   │ Free Data    │ Public API   │ Easy         │ FREE         │
│ Indeed              │ Coverage     │ Partner API  │ Medium       │ $$           │
│ StepStone           │ Coverage     │ Partner API  │ Medium       │ $$           │
│ Monster             │ Supplement   │ RSS Feeds    │ Easy         │ FREE         │
│ Xing                │ DACH Network │ 3rd Party    │ Medium       │ $            │
│ LinkedIn            │ Enterprise   │ Paid API     │ Hard         │ $$$          │
│ CareerBuilder       │ EU Hosting   │ Developer    │ Medium       │ $            │
│ Glassdoor           │ Reviews      │ None         │ Very Hard    │ N/A          │
│ Jobware             │ Executives   │ Unknown      │ Unknown      │ ?            │
│ Dice                │ ❌ Avoid     │ None         │ -            │ -            │
└─────────────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

---

## The 80/20 Solution

### Start Here (Covers ~80% of German Job Market)

**Phase 1: Free Foundation (Week 1)**
```
1. Arbeitsagentur API (1.5M+ jobs, official gov data)
   └─ Implementation: 1-2 days
   └─ Cost: $0
   └─ Coverage: Government jobs + all registered positions

2. Monster RSS (supplement data)
   └─ Implementation: 1 day
   └─ Cost: $0
   └─ Coverage: #3 job board
```

**Phase 2: Commercial Coverage (Month 1-2)**
```
3. Indeed Partnership (#1 job board)
   └─ Implementation: 1-2 weeks (+ partnership process)
   └─ Cost: $$-$$$ (contact for pricing)
   └─ Coverage: Largest job board in Germany

4. StepStone Partnership (#2 job board)
   └─ Implementation: 1-2 weeks (+ partnership process)
   └─ Cost: $$-$$$ (contact for pricing)
   └─ Coverage: 9.53M monthly visits, 39.4% market share
```

**Total Coverage:** ~95% of German online job market

---

## Quick Implementation Guide

### 1. Arbeitsagentur (Quickest Start - 2 Hours)

**API Endpoint:**
```
https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs
```

**Minimal Working Example:**
```python
import requests

headers = {"X-API-Key": "jobboerse-jobsuche"}
params = {
    "was": "Software Developer",  # Job title search
    "wo": "Berlin",                # Location
    "page": 1                      # Page number
}

response = requests.get(
    "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobs",
    headers=headers,
    params=params
)

jobs = response.json()
print(f"Found {len(jobs.get('stellenangebote', []))} jobs")
```

**Rate Limit:** 1,000 requests/hour
**Documentation:** https://jobsuche.api.bund.dev/

---

### 2. Monster RSS (Quickest Supplement - 1 Hour)

**Setup:**
1. Create search on monster.de
2. Get RSS feed URL from search results
3. Parse with feedparser

**Minimal Working Example:**
```python
import feedparser

# Configure your search on monster.de and get RSS URL
rss_url = "https://www.monster.de/jobs/search/rss?..."

feed = feedparser.parse(rss_url)

for entry in feed.entries:
    print(f"Title: {entry.title}")
    print(f"Link: {entry.link}")
    print(f"Published: {entry.published}")
    print("---")
```

---

### 3. Indeed Partnership (Best Coverage - 2-4 Weeks Setup)

**Process:**
1. Visit: https://docs.indeed.com/
2. Apply for partnership
3. Provide use case and expected volume
4. Negotiate pricing
5. Receive API credentials
6. Implement OAuth 2.0

**Expected Timeline:**
- Application: 1 week
- Approval: 1-2 weeks
- Implementation: 3-5 days

---

## Technical Decision Tree

```
START: Need German Job Data
│
├─ Budget Available?
│  │
│  ├─ NO → Use Free Options
│  │        └─ Arbeitsagentur API + Monster RSS
│  │           └─ Coverage: ~50-60% of market
│  │
│  └─ YES → What's the budget?
│     │
│     ├─ < $500/month
│     │  └─ Arbeitsagentur + Monster + Xing 3rd Party
│     │     └─ Coverage: ~60-70% of market
│     │
│     ├─ $500-$2,000/month
│     │  └─ Above + Indeed Partnership (likely range)
│     │     └─ Coverage: ~80-90% of market
│     │
│     └─ > $2,000/month
│        └─ Above + StepStone + LinkedIn
│           └─ Coverage: ~95%+ of market
│
└─ Need Professional Network Data (Profiles)?
   │
   ├─ DACH Focus → Xing (3rd party APIs)
   └─ Global Focus → LinkedIn ($$$ API)
```

---

## API Availability Summary

### ✅ Available & Recommended

| Platform | API Type | Auth | Docs | Cost | Start Here |
|----------|----------|------|------|------|------------|
| **Arbeitsagentur** | REST | API Key | Good | Free | ⭐ YES |
| **Indeed** | REST/GraphQL | OAuth 2.0 | Excellent | Paid | Partnership |
| **StepStone** | XML | Credentials | Good | Paid | Partnership |
| **Monster** | RSS | None | N/A | Free | ⭐ YES (RSS) |

### ⚠️ Available with Limitations

| Platform | API Type | Auth | Limitation | Cost |
|----------|----------|------|------------|------|
| **LinkedIn** | REST | OAuth 2.0 | Enterprise only | $$$$ |
| **CareerBuilder** | REST/XML | API Key | US-focused docs | $$ |
| **Xing** | 3rd Party | Varies | No official API | $ |

### ❌ Not Available

| Platform | Status | Alternative |
|----------|--------|-------------|
| **Glassdoor** | Closed 2021 | None (partners only) |
| **Jobware** | Unknown | Contact directly |
| **Dice** | Shutdown | Use others |

---

## Anti-Scraping Protection Levels

### 🔴 Very Hard - Don't Scrape
- **Glassdoor** - Cloudflare, login walls, AI detection
- **LinkedIn** - Extremely aggressive, legal action
- **Indeed** - Strong detection, IP bans, legal risk

### 🟡 Medium - Use API Instead
- **StepStone** - Cloudflare, but API available
- **CareerBuilder** - Standard protection, API exists
- **Xing** - JS-heavy, use 3rd party APIs

### 🟢 Easy - But API is Better
- **Arbeitsagentur** - Moderate protection, free API exists
- **Monster** - Standard protection, use RSS instead

---

## Data Field Comparison

### Job Posting Core Fields

| Field | Arbeitsagentur | Indeed | StepStone | Monster | LinkedIn |
|-------|----------------|--------|-----------|---------|----------|
| **Title** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Description** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Location** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Company** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Salary** | ⚠️ Sometimes | ⚠️ Sometimes | ⚠️ Sometimes | ⚠️ Sometimes | ⚠️ Sometimes |
| **Posted Date** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Job Type** | ✅ | ✅ | ✅ | ✅ | ✅ |
| **Experience** | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| **Benefits** | ⚠️ | ✅ | ✅ | ⚠️ | ✅ |
| **Remote** | ✅ | ✅ | ✅ | ✅ | ✅ |

### Special Features

| Platform | Unique Data |
|----------|-------------|
| **Arbeitsagentur** | Official gov job IDs, temp staffing flag |
| **Indeed** | Job source tracking, disposition data |
| **StepStone** | Work field taxonomy, channel targeting |
| **LinkedIn** | Professional profiles, company insights |
| **Glassdoor** | Company reviews, salary reports, interview insights |
| **Xing** | DACH professional network, company communities |

---

## Rate Limits Quick Reference

| Platform | Free Tier | Paid Tier | Time Window |
|----------|-----------|-----------|-------------|
| **Arbeitsagentur** | 1,000 | N/A | per hour |
| **Indeed** | 100-500 | Custom | per day |
| **LinkedIn** | 100 | 100K-1M+ | per day |
| **StepStone** | N/A | Custom | Partner agreement |
| **Monster** | RSS refresh | N/A | Feed-based |
| **CareerBuilder** | Custom | Custom | Not disclosed |

---

## Legal Risk Assessment

### Low Risk ✅
- Using official APIs with proper authentication
- Reading public RSS feeds
- Respecting robots.txt
- Staying within rate limits

### Medium Risk ⚠️
- Scraping with robots.txt approval
- Third-party API services
- Arbeitsagentur API (unofficial community docs)

### High Risk ❌
- Scraping with robots.txt disallow
- Circumventing anti-bot measures
- Exceeding rate limits
- Ignoring Terms of Service
- Indeed/LinkedIn/Glassdoor scraping

---

## Cost Estimates (2025)

### Free Tier ($0/month)
**Platforms:** Arbeitsagentur API, Monster RSS
**Coverage:** 50-60% of market
**Limitations:** Limited data fields, no support

### Startup Tier ($100-500/month estimate)
**Platforms:** Above + Xing 3rd party + Basic scraping services
**Coverage:** 60-70% of market
**Limitations:** Some data gaps, community support

### Business Tier ($500-2,000/month estimate)
**Platforms:** Above + Indeed Partnership
**Coverage:** 80-90% of market
**Limitations:** Some platforms still missing

### Enterprise Tier ($2,000-10,000+/month estimate)
**Platforms:** Indeed + StepStone + LinkedIn + CareerBuilder
**Coverage:** 95%+ of market
**Limitations:** Very expensive

*Note: Actual costs depend on volume, use case, and negotiations*

---

## Market Coverage Strategy

### Minimum Viable Coverage (60%)
```
1. Arbeitsagentur API (free)
2. Monster RSS (free)
```
**Best For:** Personal projects, research, MVPs
**Time to Implement:** 1-2 days
**Cost:** $0

### Recommended Coverage (85%)
```
1. Arbeitsagentur API
2. Indeed Partnership
3. Monster RSS
4. Xing 3rd Party API
```
**Best For:** Job boards, recruitment tools, market analysis
**Time to Implement:** 3-4 weeks (including partnership)
**Cost:** $500-2,000/month (estimate)

### Maximum Coverage (95%+)
```
1. Arbeitsagentur API
2. Indeed Partnership
3. StepStone Partnership
4. LinkedIn API
5. Xing 3rd Party
6. Monster RSS
7. CareerBuilder API
```
**Best For:** Enterprise recruitment platforms, comprehensive market intelligence
**Time to Implement:** 2-3 months
**Cost:** $2,000-10,000+/month

---

## Red Flags - Avoid These Approaches

❌ **Don't:**
1. Scrape Indeed - They will ban you and may sue
2. Scrape Glassdoor - Nearly impossible, high legal risk
3. Scrape LinkedIn - Very aggressive legal action
4. Use Dice for German market - Closed operations
5. Ignore robots.txt - Legal risk in Germany
6. Exceed rate limits - Quick way to get banned
7. Circumvent CAPTCHAs - ToS violation
8. Skip GDPR compliance - Legal requirement in EU

---

## GDPR Compliance Checklist

For any German job data collection:

- [ ] Legal basis for processing (legitimate interest/consent)
- [ ] Privacy policy published
- [ ] Data minimization (only collect what's needed)
- [ ] User rights implemented (access, deletion, portability)
- [ ] Data retention policy defined
- [ ] Security measures in place
- [ ] DPO appointed (if required)
- [ ] DPIA completed (if high risk)
- [ ] Third-party processors vetted
- [ ] Data transfer safeguards (if non-EU)

---

## When to Contact Platforms Directly

**Contact for:**
- Volume > 10,000 requests/day
- Commercial use cases
- Need historical data
- Require SLA guarantees
- Enterprise features needed
- Custom data fields required
- White-label solutions
- Dedicated support

**Platforms to Contact:**
1. **Indeed:** Partnership team via docs.indeed.com
2. **StepStone:** Business development via api.stepstone.com
3. **LinkedIn:** Partnership application process
4. **Jobware:** jobs@jobware.de

---

## Recommended Architecture

### For Small Projects (<10K jobs/day)
```
Python + Requests + PostgreSQL
├── Arbeitsagentur API (cron every 4 hours)
├── Monster RSS (cron every 6 hours)
└── Simple PostgreSQL storage
```

### For Medium Projects (10K-100K jobs/day)
```
Python + FastAPI + Celery + Redis + PostgreSQL
├── Arbeitsagentur API (worker)
├── Indeed API (worker)
├── Monster RSS (worker)
├── Xing 3rd Party (worker)
├── Celery beat (scheduling)
└── PostgreSQL + Redis (storage + cache)
```

### For Large Projects (>100K jobs/day)
```
Python/Go Microservices + Kafka + PostgreSQL + Redis + Elasticsearch
├── API Gateway (rate limiting, auth)
├── Job Scrapers (separate services per source)
├── Kafka (message queue)
├── Data Normalization Service
├── Deduplication Service
├── PostgreSQL (primary storage)
├── Elasticsearch (search)
└── Redis (caching, rate limiting)
```

---

## Testing & Validation Checklist

Before going to production:

**API Integration:**
- [ ] Rate limiting tested and working
- [ ] Error handling for all API endpoints
- [ ] Retry logic with exponential backoff
- [ ] Circuit breaker pattern implemented
- [ ] Monitoring and alerting set up
- [ ] Data validation with Pydantic or similar
- [ ] Deduplication logic tested
- [ ] Schema change detection

**Legal & Compliance:**
- [ ] Terms of Service reviewed
- [ ] robots.txt compliance verified
- [ ] GDPR compliance implemented
- [ ] Privacy policy published
- [ ] Data retention policy implemented
- [ ] Legal counsel review (if commercial)

**Quality Assurance:**
- [ ] Data accuracy spot-checked
- [ ] Duplicate detection working
- [ ] Location normalization tested
- [ ] Date parsing verified
- [ ] Missing data handling
- [ ] Edge cases covered

---

## Support & Resources

### Official Documentation
- **Arbeitsagentur:** https://jobsuche.api.bund.dev/
- **Indeed:** https://docs.indeed.com/
- **StepStone:** https://api.stepstone.com/
- **LinkedIn:** https://learn.microsoft.com/en-us/linkedin/
- **CareerBuilder:** http://api.careerbuilder.com/

### Community Resources
- **bundesAPI (Arbeitsagentur):** https://github.com/bundesAPI/jobsuche-api
- **Stack Overflow:** Tag [web-scraping] [job-boards]

### Legal Resources
- **GDPR Official:** https://gdpr.eu/
- **German DPA:** https://www.bfdi.bund.de/
- **EU Data Protection:** https://edpb.europa.eu/

---

## Next Steps

1. **Define Requirements:**
   - What's your budget?
   - How many jobs/day do you need?
   - What markets/industries?
   - Commercial or personal use?

2. **Start Small:**
   - Week 1: Implement Arbeitsagentur API
   - Week 2: Add Monster RSS
   - Week 3: Test and validate data quality
   - Week 4: Decide on commercial partnerships

3. **Scale Up:**
   - Month 2: Apply for Indeed partnership
   - Month 3: Implement Indeed API
   - Month 4: Evaluate StepStone/LinkedIn
   - Month 5+: Add remaining sources as needed

4. **Maintain:**
   - Quarterly ToS review
   - Monthly data quality checks
   - Weekly monitoring of API status
   - Annual legal compliance review

---

**Document Version:** 1.0
**Last Updated:** November 20, 2025

*For detailed analysis, see: German_Job_Boards_API_Analysis.md*
