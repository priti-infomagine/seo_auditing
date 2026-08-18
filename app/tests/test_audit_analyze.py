"""
Integration tests for the Audit Analyze API endpoint.

Tests the POST /api/v1/audit/analyze endpoint:
1. Successful complete crawl → parse → score pipeline (returns unified response)
2. Invalid URL returns validation error / runtime error
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_audit_analyze_success():
    """
    Test successful complete audit pipeline with a valid URL.
    Verifies the unified response shape: audit, summary, categories, issues,
    category_results, crawl, indexation, errors, metadata.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "https://www.reddit.com/"},
        )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()

    # --- audit block ---
    audit = data["audit"]
    assert audit["domain"] == "www.reddit.com"
    assert audit["url"] == "https://www.reddit.com/"
    assert audit["pages_crawled"] >= 1
    assert audit["pages_analyzed"] >= 1
    assert audit["pages_discovered"] >= 1
    assert audit["status"] == "completed"

    # --- summary (4-tier severity counts) ---
    summary = data["summary"]
    assert "overall_score" in summary
    assert 0 <= summary["overall_score"] <= 100
    assert summary["health"] in {"excellent", "good", "needs_attention", "poor", "critical"}
    for key in ("critical_issues", "high_issues", "medium_issues", "low_issues"):
        assert isinstance(summary[key], int)
    assert summary["passed_checks"] >= 0
    assert summary["failed_checks"] >= 0

    # --- categories ---
    categories = data["categories"]
    assert isinstance(categories, list)
    assert len(categories) >= 1
    cat_ids = {c["id"] for c in categories}
    for expected in ("on_page", "technical_seo", "content_quality", "performance"):
        assert expected in cat_ids, f"missing category {expected}"
    for c in categories:
        assert {"id", "name", "score", "status", "checks_total",
                "checks_passed", "checks_failed", "issues"} <= set(c.keys())
        assert c["issues"] == []  # detail lives in top-level issues[] + category_results

    # --- issues: strict slim shape {page_url, affected_part} ---
    issues = data["issues"]
    assert isinstance(issues, list)
    for issue in issues:
        assert set(issue.keys()) == {"page_url", "affected_part"}
        assert issue["page_url"]
        assert issue["affected_part"]

    # --- category_results ---
    category_results = data["category_results"]
    assert isinstance(category_results, dict)
    assert "on_page" in category_results
    # every sub-check has a status
    for cat_id, subchecks in category_results.items():
        for sub, check in subchecks.items():
            assert "status" in check
            assert "score" in check

    # --- crawl / indexation ---
    crawl = data["crawl"]
    assert crawl["pages_discovered"] >= 1
    assert "status_codes" in crawl
    assert "blocked_by_robots" in crawl
    indexation = data["indexation"]
    assert "indexable" in indexation
    assert "noindex" in indexation

    # --- priorities + recommendations ---
    priorities = data["priorities"]
    assert {"critical", "high", "medium", "low"} <= set(priorities.keys())
    recommendations = data["recommendations"]
    assert isinstance(recommendations, list)
    for rec in recommendations:
        assert {"priority", "rule_id", "title", "action", "effort", "affected_pages"} <= set(rec.keys())

    # --- errors + metadata ---
    assert isinstance(data["errors"], list)
    assert data["metadata"]["output_shape"] == "unified_v1"


@pytest.mark.asyncio
async def test_audit_analyze_invalid_url():
    """
    Test that an invalid/unreachable URL returns an error (runtime crawl failure).
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": "not-a-valid-url"},
        )

    # URL is auto-corrected to https://not-a-valid-url, then crawler fails with 500
    assert response.status_code == 500
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_audit_analyze_empty_url():
    """
    Test that an empty URL returns a validation error.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/audit/analyze",
            json={"url": ""},
        )

    # Pydantic validation should catch this
    assert response.status_code == 422
    assert "detail" in response.json()
