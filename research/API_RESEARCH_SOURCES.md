# German Job Boards API Research - Sources & References

**Research Date:** November 20, 2025
**Researcher:** Claude (Anthropic)

This document contains all sources and references used in the comprehensive job board API analysis.

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

## Research Methodology

### Search Strategy
- Searched for official API documentation
- Investigated third-party API alternatives
- Reviewed terms of service and legal restrictions
- Analyzed market share and relevance data
- Examined web scraping feasibility and anti-bot measures
- Evaluated rate limits and cost structures

### Time Period
- Primary research: November 2025
- Market data: 2023-2025 where available
- Some historical context included for closed services

---

## Sources by Platform

### 1. StepStone (stepstone.de)

**Official API Documentation:**
- https://api.stepstone.com/ - Main API portal
- https://api.stepstone.com/stepstone-xml-guide/ - XML API guide
- https://api.stepstone.com/knowledge-base/introduction/ - Introduction docs
- https://api.stepstone.com/full-xml-example/ - Full XML examples

**Third-Party Tools:**
- https://apify.com/jupri/stepstone-scraper/api - Scraper API
- https://github.com/EvolutionJobs/Evolution-StepStone - API wrapper
- https://support.equest.com/index.php?pg=kb.page&id=4517 - Integration guide

**Market Data:**
- https://6sense.com/tech/job-board/stepstone-market-share - Market share analysis
- https://www.similarweb.com/website/stepstone.de/ - Traffic analytics
- https://totalent.eu/stepstone-regains-ground-from-indeed-in-germany/ - Market position
- https://www.jobboardfinder.com/jobboard-stepstone-germany - Platform overview

**Key Findings:**
- XML API primarily for job posting (not search)
- 9.53M monthly visits, 39.4% market share
- #2 position in German market
- Partnership required for API access

---

### 2. Indeed Germany (indeed.de)

**Official API Documentation:**
- https://docs.indeed.com/ - Main documentation portal
- https://developer.indeed.com/ - Developer portal
- https://developer.indeed.com/docs/publisher-jobs/job-search - Job Search API
- https://docs.indeed.com/job-sync-api/job-sync-api-guide - Job Sync API guide
- https://docs.indeed.com/indeed-apply/application-data - Application data reference

**GitHub Resources:**
- https://github.com/indeedlabs/indeed-python - Python client library
- https://github.com/paulrays/indeed-jobs-api - Community wrapper

**Third-Party Documentation:**
- https://rapidapi.com/indeed/api/indeed - RapidAPI integration
- https://apix-drive.com/en/blog/other/indeed-api-integration - Integration guide

**Terms of Service & Legal:**
- https://urltotext.com/blog/2025/05/04/indeedcom-web-scraping-guide/ - Scraping policy analysis
- https://webscraping.ai/faq/indeed-scraping/ - Anti-scraping measures
- https://medium.com/@christian.gawron/im-not-a-lawyer-but-in-germany-web-scraping-has-been-ruled-legal-by-our-civil-high-court-19d996564d4 - German legal context

**Key Findings:**
- Official REST and GraphQL APIs available
- Partnership required for access
- #1 position in German market
- Scraping explicitly prohibited in ToS and robots.txt
- Strong anti-bot measures (Cloudflare, rate limiting, IP blocking)

---

### 3. LinkedIn

**Official API Documentation:**
- https://learn.microsoft.com/en-us/linkedin/ - Microsoft Learn docs
- https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access - Getting access
- https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits - Rate limits
- https://developer.linkedin.com/ - Developer portal
- https://developer.linkedin.com/product-catalog - Product catalog

**Pricing & Access:**
- https://data365.co/guides/linkedin-api-pricing - Pricing guide
- https://www.unipile.com/how-linkedin-api-pricing-works/ - Pricing breakdown
- https://medium.com/@proxycurl/the-linkedin-api-pricing-guide-you-need-and-how-to-get-access-d2bf20242944 - Access guide
- https://www.telemediaonline.co.uk/linkedin-api-pricing-what-you-need-to-know/ - Pricing info
- https://www.famelab.io/how-much-does-linkedin-api-cost/ - Cost analysis

**Community Resources:**
- https://dev.to/eunit/linkedin-jobs-api-36m7 - Jobs API overview
- https://www.getphyllo.com/post/linkedin-api-ultimate-guide-on-linkedin-api-integration - Integration guide
- https://scrupp.com/blog/linkedin-api-jobs - Guide to opportunities
- https://scrapfly.io/blog/posts/guide-to-linkedin-api-and-alternatives - Alternatives

**Key Findings:**
- OAuth 2.0 authentication
- Partnership application required
- Rate limits: 100/day free, 100K-1M+ paid
- Costs: $59-$699/month for basic APIs, $1000s for Jobs API
- Extremely restrictive access

---

### 4. Xing (xing.com)

**Third-Party APIs (No Official Public API):**
- https://www.xingzap.com/xing-scraping-api - XingZap API
- https://developer.xingzap.com/ - XingZap API reference
- https://www.piloterr.com/library/xing-search - Piloterr Xing Search
- https://www.piloterr.com/library/xing-job - Piloterr Xing Job
- https://apify.com/epctex/xing-scraper/api - Apify XING scraper
- https://www.scrapingbee.com/scrapers/xing-api/ - ScrapingBee Xing API

**Official (Non-Job) APIs:**
- https://developers.xing-events.com/index.php/REST_API_Overview - Events API only

**Community Resources:**
- https://rapidapi.com/search/xing - Various Xing APIs
- https://www.heise.de/ix/artikel/Sozial-integriert-1892413.html - Integration article (German)

**Key Findings:**
- No official public job search API
- 19M members in DACH region
- Third-party scraping APIs available
- GDPR-compliant options exist (XingZap)

---

### 5. Monster Germany (monster.de)

**API Research:**
- https://stackoverflow.com/questions/3150336/is-there-any-api-available-from-monster-for-searching-job - No public API
- https://rapidapi.com/jaypat87/api/monster1 - Third-party API
- https://rapidapi.com/bebity-bebity-default/api/monster-jobs-api - Another third-party
- https://www.experts-exchange.com/questions/27850564/Access-Monster-com-joblist-using-RSS-XML-and-or-API.html - RSS discussion

**Third-Party Scrapers:**
- https://apify.com/mscraper/monster-job-search-scraper/api - Scraper (deprecated)
- https://apify.com/bebity/monster-jobs-scraper/api - Another scraper (deprecated)
- https://github.com/ConnorSMaynes/monster - Unofficial headless API
- https://crawlbase.com/blog/how-to-scrape-monster-jobs-with-python/ - Scraping guide

**Integration:**
- https://recruiterswebsites.com/app/monster/ - Monster API integration (for recruiters)

**Key Findings:**
- No official public API
- RSS feeds available for job searches
- #3 position in German market
- Community tools exist but many deprecated

---

### 6. Glassdoor Germany (glassdoor.de)

**Official (Limited) Documentation:**
- https://www.glassdoor.com/developer/index.htm - Developer portal
- https://www.glassdoor.com/developer/jobsApiActions.htm - Jobs API (partner only)
- https://www.glassdoor.com/developer/companiesApiActions.htm - Companies API
- https://www.glassdoor.com/developer/salariesApiActions.htm - Salaries API

**API Status & History:**
- https://zuplo.com/blog/2024/09/30/what-is-glassdoor-api - API shutdown analysis
- https://cran.r-project.org/web/packages/glassdoor/vignettes/running-glassdoor.html - Historical R package

**Third-Party Alternatives:**
- https://rapidapi.com/letscrape-6bRBa3QguO5/api/real-time-glassdoor-data - Real-time API
- https://mantiks.io/job-postings-api/glassdoor - Job postings API
- https://apify.com/alexey/glassdoor-jobs-scraper - Scraper (deprecated)

**Web Scraping Guides:**
- https://scrapfly.io/blog/posts/how-to-scrape-glassdoor - Comprehensive guide (2025)
- https://www.browserless.io/blog/scrape-glassdoor-puppeteer - Puppeteer approach
- https://www.goproxy.com/blog/scraping-glassdoor/ - Scraping overview
- https://scrapeops.io/websites/glassdoor - Scraping strategies
- https://www.scrapingbee.com/blog/how-to-scrape-glassdoor/ - ScrapingBee guide
- https://brightdata.com/blog/web-data/how-to-scrape-glassdoor - Bright Data guide
- https://www.scraperapi.com/web-scraping/glassdoor/ - ScraperAPI guide

**Key Findings:**
- Public API closed in 2021
- Partner-only access now
- Very strong anti-bot measures (Cloudflare, login walls, AI detection)
- Extremely difficult to scrape (very hard rating)

---

### 7. Arbeitsagentur (arbeitsagentur.de)

**Official/Community Documentation:**
- https://jobsuche.api.bund.dev/ - Community-created OpenAPI docs
- https://github.com/bundesAPI/jobsuche-api - GitHub repository
- https://github.com/bundesAPI/jobsuche-api/blob/main/README.md - README
- https://github.com/bundesAPI/jobsuche-api/blob/main/api_example.py - Python example

**API Listings:**
- https://publicapi.dev/arbeitsamt-api - Public API directory
- https://publicapis.io/arbeitsamt-api - Another listing
- https://pypi.org/project/de-jobsuche/ - Python package

**Context & Background:**
- https://netzpolitik.org/2021/open-data-arbeitsagentur-kaempft-gegen-offene-schnittstelle/ - Open data controversy
- https://gist.github.com/LilithWittmann/f4233074c04a6f6a147ddf69252ae442 - Technical notes

**Third-Party Scrapers:**
- https://apify.com/lexis-solutions/bundesagentur-fur-arbeit-arbeitsagentur-scraper/api/javascript - Scraper API

**Key Findings:**
- Free public API available
- Endpoint: https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs
- API Key: "jobboerse-jobsuche" (in header)
- Rate limit: 1,000 requests/hour
- 1.5M+ job listings
- Unofficial community documentation (official position unclear)

---

### 8. Jobware (jobware.de)

**Platform Information:**
- https://www.jobboardfinder.com/jobboard-jobware-germany - Platform overview
- https://jobs.computerwoche.de/Jobs/Jobware-GmbH.33659.html - Company jobs

**Integration:**
- https://www.ismartrecruit.com/integration/sponsored-job-board/jobware - iSmartRecruit integration

**Job Listings:**
- https://germantechjobs.de/jobs/API/all - API developer jobs (German)
- https://germantechjobs.de/en/jobs/API/all - API developer jobs (English)
- https://www.linkedin.com/jobs/jobware-gmbh-jobs-worldwide - LinkedIn company jobs

**General Resources:**
- https://publicapis.dev/category/jobs - Job APIs category

**Key Findings:**
- Founded 1996, ~200 employees
- Focus on executive and specialized positions
- No public API information found
- Integration with recruitment systems exists
- Contact: jobs@jobware.de

---

### 9. CareerBuilder Germany

**API Documentation:**
- http://api.careerbuilder.com/Search/jobsearch/jobsearchinfo.aspx - Job search info
- https://careerbuildersearch.com/docs/job - Search APIs
- http://ws.careerbuilder.com/schemas/ - XML Web Services
- https://apitracker.io/a/careerbuilder - API tracker

**GitHub Resources:**
- https://github.com/careerbuilder/DataScienceAPIDocumentation - Data Science APIs
- https://github.com/dankerizer/CareerBuilder-API-PHP-Library - PHP library
- https://github.com/careerbuilder/ruby-cb-api - Ruby wrapper

**Third-Party:**
- https://jobapis.github.io/open-source/careerbuilder/ - JobApis client

**Germany Presence:**
- https://presse.careerbuilder.de/ - German press site
- https://www.jobboardfinder.com/jobboard-jobsde-germany - Jobs.de info
- https://www.careerbuilder.com/jobs-germany - Germany jobs
- https://workello.com/job-boards-germany/ - Job boards list
- https://en.wikipedia.org/wiki/CareerBuilder - Wikipedia

**Key Findings:**
- API exists (REST/XML)
- EU production environment available
- Operating in Germany via Jobs.de since 2011
- 75,000+ German CVs, 490,000+ European database
- Only ~490 English-language job ads
- Small market share compared to StepStone/Indeed

---

### 10. Dice (dice.com)

**Platform Information:**
- https://www.dice.com/jobs/q-German-jobs - German jobs search
- https://www.jobboardfinder.com/news/dice-goodbye-germany-goodbye-uk/ - Closure announcement
- http://sap.dice.com/browse/Browse-SAP-Jobs-in-Germany/en - SAP jobs

**API Status:**
- https://github.com/jobapis/jobs-dice - API library (shut down)
- https://stackoverflow.com/questions/24947495/cant-figure-out-how-to-access-dice-coms-rest-api - Access issues
- https://dice-talent-public.api-docs.io/ - Dice Talent API

**Job Search:**
- https://justdice.io/jobs/ - JustDice jobs
- https://dicecamp.com/jobs/ - Dicecamp jobs
- https://www.dice.com/ - Main site

**Key Findings:**
- Closed German and UK operations (summer 2018)
- Public API shut down
- Only 106 German-related jobs currently
- Shifted focus to eFinancialCareers
- NOT RECOMMENDED for German market

---

## Market Share & Statistics Sources

**Overall Market Analysis:**
- https://totalent.eu/stepstone-regains-ground-from-indeed-in-germany/ - Market dynamics
- https://6sense.com/tech/job-board/indeed-vs-stepstone - Platform comparison
- https://terratern.com/blog/job-sites-in-germany/ - Top 15 job sites
- https://talentneural.com/recruitment-hr-blog/german-job-sites.html - Best 20 German job sites
- https://www.deutschland.de/en/topic/business/job-boards-in-germany-stepstone-xing-truffls - Official overview
- https://www.ere.net/what-the-european-job-board-market-looks-like-in-2018/ - European market (2018)

**Platform-Specific:**
- https://6sense.com/tech/job-board/stepstone-market-share - StepStone: 0.47% global, 39.4% Germany
- https://www.similarweb.com/website/stepstone.de/ - StepStone traffic analytics
- https://formatera.com/germany/life/the-top-10-job-websites-and-job-portals-in-germany/ - Top 10 portals
- https://www.expatrio.com/about-germany/germany-job-search - Expat guide

**Key Market Findings:**
- Indeed: #1 in Germany
- StepStone: #2 (9.53M visits/month, 39.4% share)
- Monster: #3
- Xing: Strong DACH presence (19M members)
- LinkedIn: Growing but still behind Xing in Germany
- Arbeitsagentur: 1.5M+ job listings (official government)

---

## Anti-Bot & Web Scraping Sources

**General Anti-Bot Measures:**
- https://www.zenrows.com/blog/bypass-cloudflare - Cloudflare bypass (2025)
- https://scrapfly.io/blog/posts/how-to-bypass-cloudflare-anti-scraping - Cloudflare anti-scraping
- https://blog.cloudflare.com/declaring-your-aindependence-block-ai-bots-scrapers-and-crawlers-with-a-single-click/ - Cloudflare AI blocking
- https://www.browserless.io/blog/how-to-bypass-cloudflare-scraping - Cloudflare bypass
- https://crawlbase.com/blog/how-to-bypass-cloudfare-and-avoid-bot-detection/ - Bot detection
- https://gologin.com/blog/web-scraping-service-cloudflare-bypass/ - Web scraping service
- https://brightdata.com/blog/web-data/bypass-cloudflare-for-web-scraping - Bright Data guide

**Anti-Bot Techniques (2025):**
- https://medium.com/@datajournal/popular-anti-scraping-techniques-765473ea0451 - Top 7 techniques
- https://scrapeops.io/web-scraping-playbook/how-to-bypass-antibots/ - Bypass guide
- https://oxylabs.io/blog/scraping-experts-bypassing-anti-bot-systems - Expert strategies
- https://www.scrapeless.com/en/blog/how-to-avoid-anti-bot - 5 methods
- https://scrapelead.io/blog/9-strong-tips-to-prevent-web-scraping-in-2025/ - Prevention tips
- https://www.scraperapi.com/web-scraping/how-to-bypass-bot-detection/ - 7 proven methods
- https://www.zenrows.com/blog/bypass-bot-detection - Best methods
- https://medium.com/@sohail_saifii/web-scraping-in-2025-bypassing-modern-bot-detection-fcab286b117d - Modern detection
- https://crawlbase.com/blog/web-scraping-challenges-and-solutions/ - 10 challenges

**Platform-Specific Scraping:**
- Indeed: https://urltotext.com/blog/2025/05/04/indeedcom-web-scraping-guide/ - Safety guide
- Glassdoor: Multiple sources listed above under Glassdoor section
- General: https://www.scrapingbee.com/blog/web-scraping-without-getting-blocked/ - Avoiding blocks

**Legal Context:**
- https://medium.com/@christian.gawron/im-not-a-lawyer-but-in-germany-web-scraping-has-been-ruled-legal-by-our-civil-high-court-19d996564d4 - German BGH ruling

**Key Anti-Bot Findings:**
- Cloudflare most common (Turnstile, fingerprinting, behavior analysis)
- JavaScript challenges increasingly common
- Login walls and rate limiting standard
- AI-driven pattern detection emerging
- German courts: Scraping legal if no circumvention of technical measures

---

## Rate Limiting & API Cost Sources

**LinkedIn:**
- https://learn.microsoft.com/en-us/linkedin/shared/api-guide/concepts/rate-limits - Official rate limits
- Multiple pricing sources listed above in LinkedIn section
- Free: 100/day per user token
- Paid: 100K-1M+ per day
- Cost: $59-$10,000+/month depending on API

**Arbeitsagentur:**
- https://publicapi.dev/arbeitsamt-api - 1,000/hour limit
- 429 error when exceeded
- Free access

**Indeed:**
- https://docs.indeed.com/ - Not explicitly documented
- Community reports: 100-500/day free tier
- Partnership required for higher limits

**General API Rate Limiting:**
- https://dev.to/kraizy_amy_a80dacf26d203d/api-rate-limiting-explained-how-to-use-free-apis-without-getting-blocked-2025-4iap - Explanation
- https://docs.oracle.com/en-us/iaas/Content/Identity/sku/api-rate-limiting.htm - Oracle docs
- https://platform.openai.com/docs/guides/rate-limits - OpenAI example
- https://zuplo.com/learning-center/api-rate-limiting - Learning center
- https://getstream.io/blog/api-rate-limiting/ - How it works

---

## Additional Resources

**Job Scraping General:**
- https://www.scraperapi.com/solutions/job-boards-scraper/ - Job board scraper
- https://www.jobspikr.com/blog/guide-to-job-scraping/ - Comprehensive guide
- https://research.aimultiple.com/web-scraping-recruitment/ - Recruitment scraping
- https://apiscrapy.com/job-scraping-software/ - Job scraping software
- https://coresignal.com/blog/job-scraping/ - Everything about job scraping
- https://www.bardeen.ai/answers/how-to-web-scrape-employer-job-boards - Employer boards
- https://www.zyte.com/data-types/scrape-job-postings/ - Zyte solution
- https://hasdata.com/blog/job-scraping - Recruitment strategies
- https://scrapfly.io/use-case/jobs-web-scraping - Use cases

**German Job Market:**
- https://www.make-it-in-germany.com/en/working-in-germany/job-listings - Official portal
- https://www.ibisworld.com/germany/industry/employment-placement-agencies/969/ - Industry analysis
- https://www.expatrio.com/about-germany/top-industries-job-opportunities-in-germany - Industries

**GDPR & Legal:**
- https://gdpr.eu/ - Official GDPR site
- https://www.bfdi.bund.de/ - German Data Protection Authority
- https://edpb.europa.eu/ - European Data Protection Board

---

## Research Limitations

**Areas Requiring Direct Contact:**
1. **Exact API Pricing:** Most platforms don't publicly disclose pricing
2. **Jobware API:** No public information found - needs direct inquiry
3. **Partner Agreements:** Specific terms require individual negotiations
4. **Rate Limit Details:** Many platforms don't publish exact limits
5. **Historical Data Access:** Availability varies by platform

**Data Freshness:**
- Market share data primarily from 2023-2024
- Some platforms may have changed policies since research date
- API features may have been updated
- Pricing subject to change

**Geographic Limitations:**
- Focus on Germany-specific features
- Some global platforms may have different features in other regions
- DACH region (Germany, Austria, Switzerland) often grouped together

---

## Verification Recommendations

Before implementation, verify:
1. Current Terms of Service on each platform
2. robots.txt file status
3. API documentation for any updates
4. Pricing (contact platforms directly)
5. Rate limits (test carefully)
6. GDPR compliance requirements
7. Legal counsel review (for commercial use)

---

## Update Schedule

**Recommended Review Frequency:**
- **Monthly:** Check for ToS changes on platforms you're using
- **Quarterly:** Review market share and platform relevance
- **Annually:** Full research update including new platforms
- **As Needed:** Monitor for platform shutdowns or major changes

**Next Scheduled Review:** February 2026

---

## Contributors & Acknowledgments

**Research Conducted By:**
- Claude (Anthropic) - AI Research Assistant

**Community Resources:**
- bundesAPI project for Arbeitsagentur documentation
- Open source library maintainers
- Web scraping community guides
- Stack Overflow contributors

**Official Documentation:**
- Indeed, StepStone, LinkedIn, Arbeitsagentur teams
- Platform developer relations teams

---

## Disclaimer

This research is provided for informational purposes only.

**Important Notes:**
- Always review and comply with Terms of Service
- Consult legal counsel for commercial use
- API availability and pricing subject to change
- Market share data may be approximate
- GDPR compliance is user's responsibility
- Use at your own risk

**Not Legal Advice:**
This document does not constitute legal advice. For legal questions about web scraping, data collection, or GDPR compliance, consult a qualified attorney.

**Not Official Documentation:**
This is independent research. Always refer to official platform documentation for authoritative information.

---

**Document Version:** 1.0
**Research Date:** November 20, 2025
**Last Updated:** November 20, 2025
