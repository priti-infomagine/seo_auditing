"""
Models package.

Import all SQLAlchemy models here so Alembic can discover them:

    from app.models import *  # noqa: F401, F403
"""

# ── Auth models ──────────────────────────────────────────────────────
from app.models.auth_models.users import User  # noqa: F401
from app.models.auth_models.otp import OTP  # noqa: F401
from app.models.auth_models.refresh_token import RefreshToken  # noqa: F401
from app.models.auth_models.token_blacklist import TokenBlacklist  # noqa: F401

# ── Crawler models ───────────────────────────────────────────────────
from app.models.crawler_models.crawl_jobs import CrawlJob  # noqa: F401
from app.models.crawler_models.crawl_pages import CrawlPage  # noqa: F401
from app.models.crawler_models.crawl_config import CrawlConfig  # noqa: F401
from app.models.crawler_models.crawl_errors import CrawlError  # noqa: F401
from app.models.crawler_models.page_links import PageLink  # noqa: F401
from app.models.crawler_models.page_assets import PageAsset  # noqa: F401
from app.models.crawler_models.page_snapshots import PageSnapshot  # noqa: F401

__all__ = [
    "User",
    "OTP",
    "RefreshToken",
    "TokenBlacklist",
    "CrawlJob",
    "CrawlPage",
    "CrawlConfig",
    "CrawlError",
    "PageLink",
    "PageAsset",
    "PageSnapshot",
]
