"""Tests for the link-analysis site crawler limits."""
import asyncio
from types import SimpleNamespace

import pytest

from app.modules.seprate_checks.link_analysis.crawler import CrawlState, SiteCrawler
from app.modules.seprate_checks.link_analysis.graph import LinkGraph


@pytest.mark.asyncio
async def test_concurrent_workers_never_exceed_max_pages():
    crawler = SiteCrawler(
        canonical_url="https://example.com/",
        domain="example.com",
        max_pages=2,
    )
    state = CrawlState(graph=LinkGraph(base_host="example.com"))
    queue = asyncio.Queue()

    async def fetch(url):
        await asyncio.sleep(0)
        return SimpleNamespace(
            normalized_url=url,
            status_code=200,
            final_url=url,
            redirect_chain=[],
            content_type="text/plain",
            error_type=None,
            success=True,
        )

    crawler._safe_fetch = fetch
    await asyncio.gather(*(
        crawler._process_url(
            f"https://example.com/page-{index}",
            0,
            state,
            None,
            queue,
        )
        for index in range(10)
    ))

    assert state.pages_crawled == 2
    assert state.pages_reserved == 2
    assert len(state.graph.pages) == 2
    assert state.crawl_truncated is True


@pytest.mark.asyncio
async def test_sitemap_urls_omitted_by_page_cap_mark_crawl_truncated():
    crawler = SiteCrawler(
        canonical_url="https://example.com/",
        domain="example.com",
        max_pages=1,
    )

    async def discover():
        return SimpleNamespace(
            sitemaps=[SimpleNamespace(urls=["https://example.com/a", "https://example.com/b"])],
            robots=SimpleNamespace(exists=False, content=None),
        )

    async def fetch(url):
        return SimpleNamespace(
            normalized_url=url,
            status_code=200,
            final_url=url,
            redirect_chain=[],
            content_type="text/plain",
            error_type=None,
            success=True,
        )

    crawler.discover = discover
    crawler._safe_fetch = fetch
    result = await crawler._run_crawl()

    assert result.pages_crawled == 1
    assert result.crawl_truncated is True