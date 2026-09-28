"""Tests for the link analysis recommendation builder."""
import pytest

from app.modules.seprate_checks.link_analysis.analyzer import FindingCandidate, SourceInfo
from app.modules.seprate_checks.link_analysis.model import (
    FindingCategory,
    FindingType,
    LinkAnalysisSeverity,
)
from app.modules.seprate_checks.link_analysis.graph import RedirectInfo
from app.modules.seprate_checks.link_analysis.recommendations import build_recommendation


def _candidate(ftype: FindingType, **kw) -> FindingCandidate:
    defaults = dict(
        category=FindingCategory.STANDARD,
        type=ftype,
        severity=LinkAnalysisSeverity.LOW,
        target_url="https://example.com/broken-page",
        status_code=None,
        final_url=None,
        sources=[],
        extra=None,
        redirect_chain=None,
        error_type=None,
    )
    defaults.update(kw)
    return FindingCandidate(**defaults)


class TestBuildRecommendation:
    def test_broken_internal_recommendation(self):
        cand = _candidate(
            FindingType.BROKEN_INTERNAL,
            severity=LinkAnalysisSeverity.HIGH,
            status_code=404,
            sources=[SourceInfo("https://example.com/home", "home", [])],
            error_type="timeout",
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Fix broken internal links"
        assert rec["priority"] == "high"
        assert rec["where_to_fix"] == "source_pages"
        assert len(rec["fix_steps"]) >= 2
        assert "SEOAudit-Bot" not in rec["fix_steps"][0]

    def test_broken_external_recommendation(self):
        cand = _candidate(
            FindingType.BROKEN_EXTERNAL,
            severity=LinkAnalysisSeverity.MEDIUM,
            status_code=500,
            sources=[SourceInfo("https://example.com/page", "link", [])],
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Update or remove broken external links"
        assert rec["priority"] == "medium"

    def test_redirect_internal_with_final_url(self):
        chain = [RedirectInfo(url="https://example.com/old", status_code=301, location="/new")]
        cand = _candidate(
            FindingType.REDIRECT_INTERNAL,
            final_url="https://example.com/new",
            redirect_chain=chain,
            sources=[SourceInfo("https://example.com/home", "link", [])],
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["suggested_target_url"] == "https://example.com/new"

    def test_redirect_external_with_final_url(self):
        cand = _candidate(
            FindingType.REDIRECT_EXTERNAL,
            final_url="https://external.com/new-path",
            redirect_chain=[],
            sources=[SourceInfo("https://example.com/page", "link", [])],
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["suggested_target_url"] == "https://external.com/new-path"

    def test_orphan_recommendation_sitemap_origin(self):
        cand = _candidate(
            FindingType.ORPHAN,
            extra={"sitemap_origin": True, "crawl_truncated": False, "inbound_count": 0, "total_sources": 0},
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Add internal links to orphan pages"

    def test_orphan_with_crawl_truncated_note(self):
        cand = _candidate(
            FindingType.ORPHAN,
            extra={"sitemap_origin": True, "crawl_truncated": True, "inbound_count": 0, "total_sources": 0},
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert any("truncated" in step for step in rec["fix_steps"])

    def test_sitemap_url_error_recommendation(self):
        cand = _candidate(
            FindingType.SITEMAP_URL_ERROR,
            status_code=404,
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["where_to_fix"] == "sitemap"

    def test_deep_page_recommendation(self):
        cand = _candidate(
            FindingType.DEEP_PAGE,
            category=FindingCategory.OPTIMIZATION,
            extra={"depth": 5, "threshold": 3},
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["where_to_fix"] == "content"

    def test_dead_end_page_recommendation(self):
        cand = _candidate(
            FindingType.DEAD_END_PAGE,
            category=FindingCategory.OPTIMIZATION,
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Add navigation links to dead-end pages"

    def test_empty_anchor_recommendation(self):
        cand = _candidate(FindingType.EMPTY_ANCHOR, category=FindingCategory.OPTIMIZATION)
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Add descriptive anchor text to links"

    def test_generic_anchor_recommendation(self):
        cand = _candidate(
            FindingType.GENERIC_ANCHOR,
            category=FindingCategory.OPTIMIZATION,
            extra={"anchor_text": "click here"},
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Replace generic anchor text with descriptive text"

    def test_nofollow_internal_recommendation(self):
        cand = _candidate(
            FindingType.NOFOLLOW_INTERNAL,
            category=FindingCategory.OPTIMIZATION,
            sources=[SourceInfo("https://example.com/a", "link", ["nofollow"])],
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Remove nofollow from internal links"

    def test_insecure_link_recommendation(self):
        cand = _candidate(
            FindingType.INSECURE_LINK,
            category=FindingCategory.OPTIMIZATION,
            sources=[SourceInfo("https://example.com/home", "link", [])],
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Use HTTPS for all internal links"

    def test_excessive_outlinks_recommendation(self):
        cand = _candidate(
            FindingType.EXCESSIVE_OUTLINKS,
            category=FindingCategory.OPTIMIZATION,
            extra={"outlink_count": 200, "threshold": 150},
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert rec["title"] == "Reduce number of links per page"

    def test_redirect_no_final_url_no_suggestion(self):
        chain = [RedirectInfo(url="https://example.com/old", status_code=302, location="/new")]
        cand = _candidate(
            FindingType.REDIRECT_INTERNAL,
            final_url=None,
            redirect_chain=chain,
            sources=[SourceInfo("https://example.com/home", "link", [])],
        )
        rec = build_recommendation(cand)
        assert rec is not None
        assert "suggested_target_url" not in rec
