"""
Integration tests for the synchronous test-crawler API endpoint.

Tests POST /api/v1/crawler/test-crawler:
1. Successful synchronous crawl returns 200 with full data
2. Invalid URL returns 422
3. Unauthenticated request returns 401
4. Response contains expected fields (pages, errors, config)
5. Failed crawl returns structured error response
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest
from httpx import ASGITransport, AsyncClient
from uuid import UUID

from app.main import app
from app.modules.crawler.schemas.crawler_schemas import TestCrawlResponse


class TestTestCrawlerEndpoint:
    @pytest.mark.asyncio
    async def test_successful_sync_crawl(self, authenticated_client: AsyncClient):
        """
        Test that a successful synchronous crawl returns 200 with full data.
        """
        response = await authenticated_client.post(
            "/api/v1/crawler/test-crawler",
            json={
                "url": "https://example.com",
                "max_depth": 1,
                "max_pages": 5,
                "concurrency": 2,
            },
        )

        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

        data = response.json()
        assert data["success"] is True
        assert data["status"] == "completed"
        assert data["url"] == "https://example.com/"
        assert data["domain"] == "example.com"
        assert "crawl_id" in data
        assert "pages_crawled" in data
        assert "total_errors" in data
        assert "duration_ms" in data
        assert "started_at" in data
        assert "completed_at" in data
        assert "pages" in data
        assert "errors" in data
        assert "crawl_config" in data

        crawl_id = UUID(data["crawl_id"])
        assert data["status"] == "completed"
        assert data["domain"] == "example.com"

    @pytest.mark.asyncio
    async def test_response_contains_crawl_config(self, authenticated_client: AsyncClient):
        """
        Test that the response includes the crawl configuration.
        """
        response = await authenticated_client.post(
            "/api/v1/crawler/test-crawler",
            json={
                "url": "https://example.com",
                "max_depth": 2,
                "max_pages": 10,
                "concurrency": 3,
            },
        )

        assert response.status_code == 200
        data = response.json()
        config = data["crawl_config"]
        assert config["max_depth"] == 2
        assert config["max_pages"] == 10
        assert config["concurrency"] == 3

    @pytest.mark.asyncio
    async def test_response_pages_have_links(self, authenticated_client: AsyncClient):
        """
        Test that crawled pages include their discovered links.
        """
        response = await authenticated_client.post(
            "/api/v1/crawler/test-crawler",
            json={
                "url": "https://example.com",
                "max_depth": 1,
                "max_pages": 5,
                "concurrency": 2,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["pages_crawled"] >= 1

        first_page = data["pages"][0]
        assert "url" in first_page
        assert "status_code" in first_page
        assert "depth" in first_page
        assert "is_success" in first_page
        assert "links" in first_page

    @pytest.mark.asyncio
    async def test_invalid_url_returns_422(self, authenticated_client: AsyncClient):
        """
        Test that an invalid URL returns 422 validation error.
        """
        response = await authenticated_client.post(
            "/api/v1/crawler/test-crawler",
            json={"url": "not-a-valid-url"},
        )

        assert response.status_code == 422
        assert "detail" in response.json()

    @pytest.mark.asyncio
    async def test_missing_url_returns_422(self, authenticated_client: AsyncClient):
        """
        Test that a missing URL returns 422 validation error.
        """
        response = await authenticated_client.post(
            "/api/v1/crawler/test-crawler",
            json={},
        )

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert any("url" in str(item.get("loc", [])) for item in detail)

    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self):
        """
        Test that unauthenticated requests return 401.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/crawler/test-crawler",
                json={"url": "https://example.com"},
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_success_field_matches_status(self, authenticated_client: AsyncClient):
        """
        Test that the success field is True only when status is completed.
        """
        response = await authenticated_client.post(
            "/api/v1/crawler/test-crawler",
            json={
                "url": "https://example.com",
                "max_depth": 1,
                "max_pages": 5,
                "concurrency": 2,
            },
        )

        assert response.status_code == 200
        data = response.json()
        if data["status"] == "completed":
            assert data["success"] is True
        elif data["status"] == "failed":
            assert data["success"] is False

