"""
Integration test for CrawlScheduler dynamic URL discovery.

Tests that when worker discovers new URLs (A -> B, C; B -> D),
all nodes A, B, C, D are crawled and the queue terminates cleanly.
"""
import asyncio

import pytest

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.services.crawl_scheduler import CrawlScheduler
from app.modules.crawler.types import DiscoveredURL


class TestSchedulerRecursion:
    @pytest.mark.asyncio
    async def test_dynamic_discovery_terminates(self):
        crawled = []

        async def worker(item: DiscoveredURL) -> None:
            crawled.append(item.normalized_url)
            if item.normalized_url == "https://example.com/a":
                scheduler.submit_discovered_url(
                    url="https://example.com/b",
                    source_url=item.normalized_url,
                    source_type="html_link",
                    depth=item.depth + 1,
                )
                scheduler.submit_discovered_url(
                    url="https://example.com/c",
                    source_url=item.normalized_url,
                    source_type="html_link",
                    depth=item.depth + 1,
                )
            elif item.normalized_url == "https://example.com/b":
                scheduler.submit_discovered_url(
                    url="https://example.com/d",
                    source_url=item.normalized_url,
                    source_type="html_link",
                    depth=item.depth + 1,
                )

        scheduler = CrawlScheduler(
            config=CrawlConfig(max_depth=3, max_pages=100, http_concurrency=2, browser_concurrency=1),
            worker_func=worker,
            base_domain="example.com",
        )
        scheduler.submit_seed("https://example.com/a")

        await scheduler.run()

        assert "https://example.com/a" in crawled
        assert "https://example.com/b" in crawled
        assert "https://example.com/c" in crawled
        assert "https://example.com/d" in crawled
        assert len(crawled) == 4
