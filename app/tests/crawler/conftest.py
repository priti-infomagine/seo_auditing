"""
Shared fixtures for crawler module tests.
"""
import sys
from pathlib import Path

import pytest
import pytest_asyncio

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def sample_html_basic():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Test Page</title>
    <meta name="description" content="A test page">
    <meta name="robots" content="index, follow">
    <link rel="canonical" href="https://example.com/test">
</head>
<body>
    <h1>Hello World</h1>
    <p>This is a test paragraph.</p>
    <a href="/page1">Internal Link</a>
    <a href="https://external.com">External</a>
    <img src="/img.jpg" alt="test image">
    <script src="/app.js"></script>
    <link rel="stylesheet" href="/style.css">
</body>
</html>"""


@pytest.fixture
def sample_html_full_seo():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Full SEO Test - Best Platform 2024</title>
    <meta name="description" content="Complete SEO testing page with all meta tags.">
    <meta name="robots" content="index, follow, max-image-preview:large">
    <meta name="googlebot" content="index, follow">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="canonical" href="https://example.com/seo-test">
    <link rel="icon" type="image/x-icon" href="/favicon.ico">
    <meta property="og:title" content="Full SEO Test">
    <meta property="og:description" content="Complete SEO testing page">
    <meta property="og:image" content="/og-image.jpg">
    <meta property="og:url" content="https://example.com/seo-test">
    <meta property="og:type" content="website">
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="Full SEO Test Twitter">
    <link rel="alternate" hreflang="en" href="https://example.com/en">
    <link rel="alternate" hreflang="fr" href="https://example.com/fr">
    <link rel="alternate" hreflang="x-default" href="https://example.com/">
    <script type="application/ld+json">
    {"@context": "https://schema.org", "@type": "Article", "headline": "SEO Test"}
    </script>
</head>
<body>
    <header><h1>Main Title</h1></header>
    <nav>
        <a href="/">Home</a>
        <a href="/about">About</a>
        <a href="/contact">Contact</a>
    </nav>
    <main>
        <article>
            <h2>Section One</h2>
            <p>Paragraph one with SEO content.</p>
            <h3>Subsection</h3>
            <p>Paragraph two with more content.</p>
            <img src="/hero.jpg" alt="Hero image" width="800" height="600" loading="lazy">
            <img src="/missing-alt.jpg">
        </article>
    </main>
    <footer>
        <h3>Footer</h3>
        <a href="/privacy">Privacy</a>
    </footer>
    <script src="/main.js" async defer></script>
    <link rel="stylesheet" href="/main.css">
</body>
</html>"""


@pytest.fixture
def sample_html_minimal():
    return "<html><head><title>Minimal</title></head><body><p>Hi</p></body></html>"


@pytest.fixture
def sample_html_empty():
    return ""


@pytest.fixture
def sample_html_non_html():
    return '{"key": "value"}'


@pytest.fixture
def mock_fetch_result():
    """Return a factory for FetchResult-like objects."""
    from types import SimpleNamespace
    def _make(
        url="https://example.com",
        normalized_url="https://example.com",
        status_code=200,
        content=b"<html><body>test</body></html>",
        headers={"content-type": "text/html"},
        final_url="https://example.com",
        content_type="text/html",
        content_length=35,
        response_time_ms=120,
        redirect_chain=None,
        success=True,
        error=None,
        error_type=None,
    ):
        return SimpleNamespace(
            url=url,
            normalized_url=normalized_url,
            status_code=status_code,
            content=content,
            headers=headers,
            final_url=final_url,
            content_type=content_type,
            content_length=content_length,
            response_time_ms=response_time_ms,
            redirect_chain=redirect_chain or [],
            success=success,
            error=error,
            error_type=error_type,
        )
    return _make

@pytest_asyncio.fixture
async def authenticated_client(db_session):
    """
    Create an AsyncClient pre-configured with a valid Bearer token.
    Registers a fresh user and completes OTP verification.
    """
    from uuid import uuid4
    from sqlalchemy import select

    from app.modules.auth.models.users import User
    from app.modules.auth.models.otp import OTP
    from app.modules.auth.schemas.register import RegisterRequest
    from app.modules.auth.schemas.verify_otp import VerifyOTPRequest
    from app.modules.auth.services.register_service import RegisterService
    from app.modules.auth.services.verify_otp_service import VerifyOTPService
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    test_email = f"test_crawler_{uuid4().hex[:8]}@example.com"

    register_service = RegisterService(db_session)
    await register_service.execute(
        RegisterRequest(name="Test Crawler User", email=test_email, password="Test@1234")
    )

    user_result = await db_session.execute(
        select(User).where(User.email == test_email)
    )
    user = user_result.scalar_one_or_none()
    assert user is not None

    otp_result = await db_session.execute(
        select(OTP).where(OTP.user_id == user.id).order_by(OTP.created_at.desc()).limit(1)
    )
    otp_record = otp_result.scalar_one_or_none()
    assert otp_record is not None

    verify_service = VerifyOTPService(db_session)
    verify_result = await verify_service.execute(
        VerifyOTPRequest(email=test_email, otp=otp_record.otp)
    )

    access_token = verify_result.response.access_token
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {access_token}"
        yield client

