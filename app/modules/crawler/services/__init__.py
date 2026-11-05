"""
Crawler services package.

Provides services for the crawler module.
"""

from app.modules.crawler.services.fetch_service import FetchResult, fetch_page
from app.modules.crawler.services.page_crawl_service import PageCrawlService, PageCrawlResult
from app.modules.crawler.services.page_extraction_service import PageExtractionService, PageFacts
from app.modules.crawler.services.link_analysis_service import LinkAnalysisService, LinkAnalysisResult
from app.modules.crawler.services.broken_link_checker import BrokenLinkChecker, BrokenLinkStats
from app.modules.crawler.services.site_discovery_service import SiteDiscoveryService, SiteDiscoveryResult
from app.modules.crawler.services.technical_analysis_service import TechnicalAnalysisService, TechnicalAnalysisResult
from app.modules.crawler.services.crawl_persistence_service import CrawlPersistenceService
from app.modules.crawler.services.link_graph_service import LinkGraphService, LinkGraphStats, get_dead_end_pages

__all__ = [
    "FetchResult",
    "fetch_page",
    "PageCrawlService",
    "PageCrawlResult",
    "PageExtractionService",
    "PageFacts",
    "LinkAnalysisService",
    "LinkAnalysisResult",
    "BrokenLinkChecker",
    "BrokenLinkStats",
    "SiteDiscoveryService",
    "SiteDiscoveryResult",
    "TechnicalAnalysisService",
    "TechnicalAnalysisResult",
    "CrawlPersistenceService",
    "LinkGraphService",
    "LinkGraphStats",
    "get_dead_end_pages",
]
