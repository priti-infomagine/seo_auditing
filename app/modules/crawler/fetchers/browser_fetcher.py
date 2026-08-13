"""
BrowserFetcher - Fetcher implementation using Playwright browser rendering.
"""
from typing import Dict, Optional

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.fetchers.base import Fetcher
from app.modules.crawler.rendering.playwright_renderer import PlaywrightRenderer
from app.modules.crawler.types import FetchResult, RedirectInfo


class BrowserFetcher(Fetcher):
    """Fetcher implementation backed by PlaywrightRenderer."""

    def __init__(self, config: Optional[CrawlConfig] = None):
        self.config = config or CrawlConfig()
        self.renderer = PlaywrightRenderer(self.config)

    async def fetch(
        self,
        url: str,
        *,
        timeout: Optional[float] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> FetchResult:
        render_res = await self.renderer.render(url, reason="browser_fetcher_direct", headers=headers)
        content_bytes = render_res.html.encode("utf-8")

        return FetchResult(
            url=url,
            normalized_url=render_res.final_url or url,
            status_code=render_res.status_code or 200,
            content=content_bytes,
            headers=render_res.headers,
            final_url=render_res.final_url or url,
            content_type=render_res.headers.get("content-type", "text/html"),
            content_length=len(content_bytes),
            response_time_ms=render_res.response_time_ms,
            redirect_chain=[],
            success=render_res.status_code == 200 or len(render_res.html) > 0,
            error=render_res.console_errors[0] if render_res.console_errors and render_res.status_code == 0 else None,
            error_type="browser_render_error" if render_res.status_code == 0 else None,
            render_mode="browser",
            render_reason=render_res.render_reason,
        )
