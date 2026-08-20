"""
PlaywrightRenderer - Executes browser rendering and returns RenderResult.
"""
import time
from typing import Dict, List, Optional

from app.modules.crawler.config import CrawlConfig
from app.modules.crawler.rendering.browser_pool import PLAYWRIGHT_AVAILABLE, BrowserPool
from app.modules.crawler.types import RenderResult


class PlaywrightRenderer:
    """Renders web pages using Playwright browser context."""

    def __init__(self, config: Optional[CrawlConfig] = None):
        self.config = config or CrawlConfig()
        self.pool = BrowserPool.get_instance(self.config)

    async def render(
        self,
        url: str,
        reason: str = "insufficient_http_content",
        headers: Optional[Dict[str, str]] = None,
    ) -> RenderResult:
        if not PLAYWRIGHT_AVAILABLE:
            return RenderResult(
                requested_url=url,
                final_url=url,
                status_code=0,
                html="",
                headers={},
                response_time_ms=0,
                render_mode="browser",
                render_reason="playwright_not_installed",
                console_errors=["Playwright package is not installed"],
            )

        start_time = time.perf_counter()
        console_errors: List[str] = []
        js_errors: List[str] = []
        failed_requests: List[Dict] = []
        response_headers: Dict[str, str] = {}
        status_code = 200

        async with self.pool.get_page() as page:
            if not page:
                return RenderResult(
                    requested_url=url,
                    final_url=url,
                    status_code=0,
                    html="",
                    headers={},
                    response_time_ms=int((time.perf_counter() - start_time) * 1000),
                    render_mode="browser",
                    render_reason="browser_acquisition_failed",
                    console_errors=["Could not acquire browser page"],
                )

            # Event listeners
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: js_errors.append(str(exc)))
            page.on("requestfailed", lambda req: failed_requests.append({
                "url": req.url,
                "failure": req.failure.error_text if (req.failure and hasattr(req.failure, "error_text")) else (str(req.failure) if req.failure else "unknown"),
            }))

            try:
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=self.config.browser_timeout * 1000,
                )
                if response:
                    status_code = response.status
                    response_headers = {k.lower(): v for k, v in (await response.all_headers()).items()}

                # Wait for network idle or fallback timeout
                try:
                    await page.wait_for_load_state("networkidle", timeout=5000)
                except Exception:
                    pass

                html_content = await page.content()
                final_url = page.url
                response_time_ms = int((time.perf_counter() - start_time) * 1000)

                return RenderResult(
                    requested_url=url,
                    final_url=final_url,
                    status_code=status_code,
                    html=html_content,
                    headers=response_headers,
                    response_time_ms=response_time_ms,
                    render_mode="browser",
                    render_reason=reason,
                    console_errors=console_errors,
                    js_errors=js_errors,
                    failed_requests=failed_requests,
                )

            except Exception as exc:
                response_time_ms = int((time.perf_counter() - start_time) * 1000)
                return RenderResult(
                    requested_url=url,
                    final_url=url,
                    status_code=0,
                    html="",
                    headers={},
                    response_time_ms=response_time_ms,
                    render_mode="browser",
                    render_reason=f"render_exception:{str(exc)}",
                    console_errors=console_errors + [str(exc)],
                    js_errors=js_errors,
                    failed_requests=failed_requests,
                )
