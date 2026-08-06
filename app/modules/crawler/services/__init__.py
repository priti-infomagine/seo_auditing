"""
Crawler services package.

Provides WebCrawler for single-URL crawling and CrawlerService
for storage-backed crawl operations consumed by the API layer.
"""

from app.modules.crawler.services.crawler import CrawlResult, WebCrawler

__all__ = ["WebCrawler", "CrawlerService", "CrawlResult"]
