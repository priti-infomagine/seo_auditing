"""
Crawler models package.

Import all crawler models here so they are registered with the
SQLAlchemy metadata and discoverable by Alembic:

    from app.models.crawler_models import *  # noqa: F401, F403
"""

from app.modules.crawler.models.crawl_jobs import CrawlJob  # noqa: F401
from app.modules.crawler.models.crawl_pages import CrawlPage  # noqa: F401
from app.modules.crawler.models.crawl_config import CrawlConfig  # noqa: F401
from app.modules.crawler.models.crawl_errors import CrawlError  # noqa: F401
from app.modules.crawler.models.page_links import PageLink  # noqa: F401
from app.modules.crawler.models.page_assets import PageAsset  # noqa: F401
from app.modules.crawler.models.page_snapshots import PageSnapshot  # noqa: F401
from app.modules.crawler.models.page_seo_data import PageSEOData  # noqa: F401
from app.modules.crawler.models.page_resources import PageResource  # noqa: F401
from app.modules.crawler.models.page_network_data import PageNetworkData  # noqa: F401
from app.modules.crawler.models.crawl_site_data import CrawlSiteData  # noqa: F401

__all__ = [
    "CrawlJob",
    "CrawlPage",
    "CrawlConfig",
    "CrawlError",
    "PageLink",
    "PageAsset",
    "PageSnapshot",
    "PageSEOData",
    "PageResource",
    "PageNetworkData",
    "CrawlSiteData",
]
