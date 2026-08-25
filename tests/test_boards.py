"""Tests for boards.py — platform adapter URL pattern matching."""

import pytest

from job_research.boards import get_adapter


class TestIndeedAdapter:
    @pytest.fixture
    def adapter(self):
        return get_adapter("de.indeed.com")

    def test_accepts_viewjob_url(self, adapter):
        assert adapter.is_job_listing_url("https://de.indeed.com/viewjob?jk=abc123")

    def test_accepts_rc_clk_url(self, adapter):
        assert adapter.is_job_listing_url("https://de.indeed.com/rc/clk?jk=abc123")

    def test_rejects_jobs_query_url(self, adapter):
        """jobs?q=... URLs are search pages, not individual listings."""
        assert not adapter.is_job_listing_url("https://de.indeed.com/jobs?q=engineer&jk=abc")

    def test_rejects_search_page(self, adapter):
        assert not adapter.is_job_listing_url("https://de.indeed.com/AI-Engineer-Jobs-in-Berlin")

    def test_rejects_category_page(self, adapter):
        assert not adapter.is_job_listing_url("https://de.indeed.com/jobs-in-Berlin")


class TestStepStoneAdapter:
    @pytest.fixture
    def adapter(self):
        return get_adapter("stepstone.de")

    def test_accepts_stellenangebote_url(self, adapter):
        assert adapter.is_job_listing_url(
            "https://www.stepstone.de/stellenangebote--AI-Engineer-Berlin--12345"
        )

    def test_accepts_jobs_id_url(self, adapter):
        assert adapter.is_job_listing_url("https://www.stepstone.de/jobs/12345")

    def test_rejects_search_page(self, adapter):
        assert not adapter.is_job_listing_url("https://www.stepstone.de/work/ai-engineer-in-berlin")


class TestLinkedInAdapter:
    @pytest.fixture
    def adapter(self):
        return get_adapter("linkedin.com")

    def test_accepts_jobs_view_url(self, adapter):
        assert adapter.is_job_listing_url("https://www.linkedin.com/jobs/view/12345")

    def test_rejects_jobs_search_url(self, adapter):
        assert not adapter.is_job_listing_url("https://www.linkedin.com/jobs/search/?keywords=AI")


class TestFallbackAdapter:
    def test_unknown_domain_matches_any_url_on_domain(self):
        adapter = get_adapter("custom-board.de")
        assert adapter.is_job_listing_url("https://custom-board.de/some/job/page")

    def test_unknown_domain_rejects_other_domain(self):
        adapter = get_adapter("custom-board.de")
        assert not adapter.is_job_listing_url("https://other-site.com/page")

    def test_fallback_has_correct_domain(self):
        adapter = get_adapter("custom-board.de")
        assert adapter.domain == "custom-board.de"
