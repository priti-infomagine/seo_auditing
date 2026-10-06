from __future__ import annotations

from typing import Any

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.services.page_crawl_service import PageCrawlService


class CrawlerAdapter:
    """Thin adapter over the existing crawler page fetch service."""

    def __init__(self, config: CrawlConfig | None = None):
        self.config = config or CrawlConfig()
        self.service = PageCrawlService(config=self.config)

    async def fetch_page(self, url: str) -> dict[str, Any]:
        result = await self.service.crawl_page(
            url,
            timeout=int(self.config.request_timeout),
            follow_redirects=True,
            max_redirects=self.config.max_redirects,
            max_retries=2,
        )

        if result.error or result.fetch_result is None:
            return {
                "status": "failed",
                "url": url,
                "final_url": result.normalized_url or url,
                "error": result.error or "page fetch failed",
                "html": "",
                "redirect_chain": [],
                "status_code": None,
                "content_type": None,
            }

        fetch_result = result.fetch_result
        return {
            "status": "ok" if fetch_result.success else "failed",
            "url": url,
            "final_url": fetch_result.final_url or fetch_result.normalized_url or url,
            "error": fetch_result.error,
            "html": fetch_result.content.decode("utf-8", errors="replace"),
            "redirect_chain": [
                {"url": item.url, "status_code": item.status_code, "location": item.location}
                for item in fetch_result.redirect_chain
            ],
            "status_code": fetch_result.status_code,
            "content_type": fetch_result.content_type,
            "response_time_ms": fetch_result.response_time_ms,
        }
