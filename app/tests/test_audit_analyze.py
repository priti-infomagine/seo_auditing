"""
Integration tests for the Audit Analyze API endpoint.

Tests the POST /api/v1/audit/analyze endpoint:
1. Successful complete crawl → parse → score pipeline
2. Invalid URL returns validation error
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_audit_analyze_success():
    """
    Test successful complete audit pipeline with a valid URL.
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
    assert data["success"] is True
    assert data["message"] == "SEO audit completed successfully"
    assert data["url"] == "https://www.reddit.com/"
    assert data["domain"] == "cyfuture.com"

    # Verify crawl summary
    crawl = data["crawl"]
    assert crawl["url"] == "https://www.reddit.com/"
    assert crawl["domain"] == "cyfuture.com"
    assert crawl["status_code"] == 200
    assert crawl["response_time"] > 0
    assert crawl["html_size_bytes"] > 0
    assert crawl["test_number"] >= 1
    assert crawl["file_path"] is not None
    assert crawl["crawled_at"] is not None

    # Verify SEO score report
    seo_score = data["seo_score"]
    assert "overall_score" in seo_score
    assert "grade" in seo_score
    assert "categories" in seo_score
    assert "total_rules" in seo_score
    assert seo_score["total_rules"] > 0
    assert 0 <= seo_score["overall_score"] <= 100
    assert seo_score["grade"] in ["A", "B", "C", "D", "F"]

    # Verify parsed data is included
    assert "parsed_data" in data
    assert data["parsed_data"] is not None


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