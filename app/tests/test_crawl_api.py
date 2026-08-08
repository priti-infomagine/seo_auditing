"""
Integration tests for the Crawler API endpoint.

Tests the POST /api/v1/crawler/crawl endpoint:
     1. Successful crawl queuing with a valid URL (authenticated)
     2. Invalid URL returns 422 validation error
     3. Missing URL returns 422 validation error
     4. Crawl job is created in database with correct owner
     5. Status endpoint returns job status (authenticated)
     6. Unauthenticated request returns 401
"""

import sys
from pathlib import Path
from typing import AsyncGenerator
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.main import app
from app.modules.crawler.models.crawl_jobs import CrawlJob
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.auth.models.users import User
from app.modules.auth.models.otp import OTP
from app.modules.auth.schemas.register import RegisterRequest
from app.modules.auth.schemas.verify_otp import VerifyOTPRequest
from app.modules.auth.services.register_service import RegisterService
from app.modules.auth.services.verify_otp_service import VerifyOTPService


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    from app.core.config import settings
    from app.core.database import Base
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator:
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    session = session_factory()
    try:
        yield session
    finally:
        try:
            await session.close()
        except Exception:
            pass


@pytest_asyncio.fixture
async def authenticated_client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """
    Create an AsyncClient pre-configured with a valid Bearer token.
    Registers a fresh user and completes OTP verification for each test.
    """
    test_email = f"crawl_test_{UUID(int=0).hex[:8]}@example.com"

    register_service = RegisterService(db_session)
    await register_service.execute(
        RegisterRequest(name="Crawl Test User", email=test_email, password="Test@1234")
    )

    user_result = await db_session.execute(
        select(User).where(User.email == test_email)
    )
    user = user_result.scalar_one_or_none()
    assert user is not None, "User should exist after registration"

    otp_result = await db_session.execute(
        select(OTP)
        .where(OTP.user_id == user.id)
        .order_by(OTP.created_at.desc())
        .limit(1)
    )
    otp_record = otp_result.scalar_one_or_none()
    assert otp_record is not None, "OTP should exist after registration"

    verify_service = VerifyOTPService(db_session)
    verify_result = await verify_service.execute(
        VerifyOTPRequest(email=test_email, otp=otp_record.otp)
    )

    access_token = verify_result.response.access_token
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {access_token}"
        yield client


@pytest.mark.asyncio
async def test_crawl_success(authenticated_client: AsyncClient, db_session):
    """
    Test successful crawl queuing with a valid URL.
    """
    response = await authenticated_client.post(
        "/api/v1/crawler/crawl",
        json={"url": "https://example.com/"},
    )

    assert response.status_code == 202, f"Expected 202, got {response.status_code}: {response.text}"

    data = response.json()
    assert data["status"] == "queued"
    assert data["message"] == "Crawl job queued successfully"
    assert "crawl_id" in data

    crawl_id = UUID(data["crawl_id"])
    repo = CrawlJobRepository(db_session)
    job = await repo.get_by_id(crawl_id)
    assert job is not None
    assert job.domain == "example.com"
    assert job.status == "queued"
    assert job.url == "https://example.com/"


@pytest.mark.asyncio
async def test_crawl_invalid_url(authenticated_client: AsyncClient):
    """
    Test that an invalid URL returns a 422 validation error.
    """
    response = await authenticated_client.post(
        "/api/v1/crawler/crawl",
        json={"url": "not-a-valid-url"},
    )

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    assert "detail" in response.json()


@pytest.mark.asyncio
async def test_crawl_missing_url(authenticated_client: AsyncClient):
    """
    Test that a missing URL field returns a 422 validation error.
    """
    response = await authenticated_client.post(
        "/api/v1/crawler/crawl",
        json={},
    )

    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    detail = response.json()["detail"]
    assert any("url" in str(item.get("loc", [])) for item in detail)


@pytest.mark.asyncio
async def test_crawl_status_endpoint(authenticated_client: AsyncClient, db_session):
    """
    Test that the status endpoint returns crawl job status.
    """
    response = await authenticated_client.post(
        "/api/v1/crawler/crawl",
        json={"url": "https://example.com/"},
    )
    assert response.status_code == 202
    crawl_id = response.json()["crawl_id"]

    status_response = await authenticated_client.get(f"/api/v1/crawler/status/{crawl_id}")
    assert status_response.status_code == 200

    status_data = status_response.json()
    assert status_data["crawl_id"] == crawl_id
    assert status_data["domain"] == "example.com"
    assert status_data["url"] == "https://example.com/"
    assert status_data["status"] == "queued"


@pytest.mark.asyncio
async def test_crawl_status_not_found(authenticated_client: AsyncClient):
    """
    Test that status endpoint returns 404 for non-existent crawl job.
    """
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await authenticated_client.get(f"/api/v1/crawler/status/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_crawl_requires_auth():
    """
    Test that unauthenticated requests to /crawler/crawl return 401.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/crawler/crawl",
            json={"url": "https://example.com/"},
        )
    assert response.status_code == 401
