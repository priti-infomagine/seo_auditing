"""
Integration tests for the Crawler API endpoint.

Tests the POST /api/v1/crawler/crawl endpoint:
    1. Successful crawl with a valid URL
    2. Invalid URL returns 422 validation error
    3. Missing URL returns 422 validation error
    4. Crawled data is saved to storage
"""

import sys
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client for the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_crawl_success(client: AsyncClient):
    """
    Test successful crawl of a valid URL.

    Verifies:
        1. Response status is 200
        2. Response body indicates success
        3. Crawled data contains expected fields
        4. Data file is saved to storage
    """
    response = await client.post(
        "/api/v1/crawler/crawl",
        json={"url": "https://cyfuture.com/"},
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    data = response.json()
    assert data["success"] is True
    assert data["message"] == "Crawl completed successfully"
    assert data["url"] == "https://cyfuture.com/"
    assert data["domain"] == "cyfuture.com"
    assert data["test_number"] >= 1
    assert data["file_path"] is not None
    assert data["crawled_at"] is not None

    # Validate saved data summary
    assert data["data"] is not None
    assert data["data"]["status_code"] == 200
    assert data["data"]["response_time"] > 0
    assert data["data"]["html_size"] > 0


@pytest.mark.asyncio
async def test_crawl_invalid_url(client: AsyncClient):
    """
    Test that an invalid URL returns a 422 validation error.

    Verifies:
        1. Response status is 422
        2. Validation error is returned
    """
    response = await client.post(
        "/api/v1/crawler/crawl",
        json={"url": "not-a-valid-url"},
    )

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_crawl_missing_url(client: AsyncClient):
    """
    Test that a missing URL field returns a 422 validation error.

    Verifies:
        1. Response status is 422
        2. Validation error indicates missing field
    """
    response = await client.post(
        "/api/v1/crawler/crawl",
        json={},
    )

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    detail = response.json()["detail"]
    assert any("url" in str(item.get("loc", [])) for item in detail)


@pytest.mark.asyncio
async def test_crawl_saves_data_to_storage(client: AsyncClient):
    """
    Test that crawled data is actually saved to disk.

    Verifies:
        1. Crawl succeeds
        2. The file_path exists on disk
        3. The saved JSON contains valid crawl data
    """
    response = await client.post(
        "/api/v1/crawler/crawl",
        json={"url": "https://cyfuture.com/"},
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    data = response.json()

    # Verify the file was saved to disk in app/storage/crawler/
    file_path = Path(data["file_path"])
    assert file_path.exists(), f"Saved file does not exist: {file_path}"
    assert "app" in str(file_path) and "storage" in str(file_path) and "crawler" in str(file_path), \
        f"File should be saved under app/storage/crawler/, got: {file_path}"

    # Verify the file content
    import json

    with open(file_path, "r", encoding="utf-8") as f:
        saved_data = json.load(f)

    assert saved_data["requested_url"] == "https://cyfuture.com/"
    assert saved_data["final_url"] is not None
    assert saved_data["html"] is not None and len(saved_data["html"]) > 0
    assert saved_data["http"]["status_code"] == 200
    assert saved_data["http"]["response_time"] > 0
    assert "performance" in saved_data
    assert "resources" in saved_data
    assert "javascript" in saved_data
    assert "security_headers" in saved_data
    assert "ssl" in saved_data
    assert "robots" in saved_data
    assert "sitemap" in saved_data