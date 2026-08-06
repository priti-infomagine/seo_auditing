"""
Crawler package - high-level crawler service.

Provides ``WebCrawler`` for single-URL crawling and ``CrawlerService``
for storage-backed crawl operations consumed by the API layer.
"""
from app.services.crawler.crawler import CrawlResult, WebCrawler
from app.services.crawler.crawl_service import CrawlerService

__all__ = ["WebCrawler", "CrawlerService", "CrawlResult"]
