"""SERP preview rendering and artifact storage.

The preview is a separate stage from the rank check: it reads the
stored result (no provider call), renders an HTML page from
``top_results`` with the target domain highlighted, optionally
captures a screenshot with Playwright (rendering our own HTML,
never google.com), and stores both artifacts on the local
filesystem behind a swappable storage interface.
"""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.logger import logger

from app.modules.crawler.rendering.browser_pool import (
    PLAYWRIGHT_AVAILABLE,
    BrowserPool,
)

DESKTOP_VIEWPORT = {"width": 1280, "height": 800}
MOBILE_VIEWPORT = {"width": 375, "height": 667}

PREVIEW_URL_PREFIX = "/api/v1/serp/previews"
ALLOWED_FILENAMES = ("preview.html", "screenshot.png")


def _esc(value: Any) -> str:
    return html.escape("" if value is None else str(value))


def render_preview_html(
    *,
    keyword: str,
    target_domain: str,
    device: str,
    result: dict[str, Any],
) -> str:
    """Render the preview HTML for a rank result."""
    best_position = result.get("best_position")
    found = bool(result.get("found"))
    top_results = [
        item
        for item in (result.get("top_results") or [])
        if isinstance(item, dict)
        and item.get("domain") == target_domain
    ]

    position_text = (
        f"#{best_position}" if best_position is not None else "Not in top results"
    )
    layout_width = "375px" if device == "mobile" else "860px"

    rows: list[str] = []
    for item in top_results:
        is_target = (
            isinstance(item.get("domain"), str)
            and item["domain"]
            and item["domain"] == target_domain
        )
        target_class = " target" if is_target else ""
        title = _esc(item.get("title"))
        url = _esc(item.get("url"))
        domain = _esc(item.get("domain"))
        snippet = _esc(item.get("snippet"))
        position = _esc(item.get("position"))
        rows.append(
            f"""
            <li class="result{target_class}">
              <div class="position">{position}</div>
              <div class="body">
                <a class="title" href="{url}">{title}</a>
                <div class="domain">{domain}</div>
                <div class="snippet">{snippet}</div>
              </div>
            </li>"""
        )
    results_html = "\n".join(rows) or "<li class='empty'>No results</li>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SERP preview — {_esc(keyword)}</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{ font-family: Arial, Helvetica, sans-serif; margin: 0;
         background: #fff; color: #202124; }}
  .wrap {{ max-width: {layout_width}; margin: 0 auto; padding: 16px; }}
  .header {{ border-bottom: 1px solid #e0e0e0; padding-bottom: 12px;
             margin-bottom: 16px; }}
  .keyword {{ font-size: 20px; font-weight: 700; }}
  .meta {{ color: #5f6368; font-size: 13px; margin-top: 4px; }}
  .badge {{ display: inline-block; margin-top: 8px; padding: 4px 10px;
            border-radius: 12px; font-size: 13px; font-weight: 700; }}
  .badge.found {{ background: #e6f4ea; color: #137333; }}
  .badge.missed {{ background: #fce8e6; color: #c5221f; }}
  ol.results {{ list-style: none; margin: 0; padding: 0; }}
  li.result {{ display: flex; gap: 12px; padding: 10px 8px;
               border-radius: 6px; }}
  li.result.target {{ background: #fff8e1; outline: 2px solid #f9ab00; }}
  .position {{ min-width: 34px; font-weight: 700; color: #5f6368;
               text-align: right; }}
  .title {{ color: #1a0dab; font-size: 16px; text-decoration: none; }}
  .domain {{ color: #006621; font-size: 13px; }}
  .snippet {{ color: #4d5156; font-size: 14px; line-height: 1.4; }}
  li.empty {{ color: #5f6368; padding: 12px 8px; }}
</style>
</head>
<body>
<div class="wrap">
  <div class="header">
    <div class="keyword">{_esc(keyword)}</div>
    <div class="meta">
      Target domain: <strong>{_esc(target_domain)}</strong>
      &middot; device: {_esc(device)}
    </div>
    <span class="badge {'found' if found else 'missed'}">{position_text}</span>
  </div>
  <ol class="results">{results_html}
  </ol>
</div>
</body>
</html>"""


class PreviewStorage:
    """Local filesystem storage for preview artifacts.

    Swap this class for an object-storage implementation without
    touching the preview logic.
    """

    def __init__(self, base_dir: str | None = None):
        self.base_dir = Path(base_dir or settings.SERP_PREVIEW_DIR)

    def _check_dir(self, check_id: Any) -> Path:
        directory = self.base_dir / str(check_id)
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def save_html(self, check_id: Any, content: str) -> str:
        path = self._check_dir(check_id) / "preview.html"
        path.write_text(content, encoding="utf-8")
        return f"{PREVIEW_URL_PREFIX}/{check_id}/preview.html"

    def save_image(self, check_id: Any, png: bytes) -> str:
        path = self._check_dir(check_id) / "screenshot.png"
        path.write_bytes(png)
        return f"{PREVIEW_URL_PREFIX}/{check_id}/screenshot.png"

    def resolve(self, check_id: Any, filename: str) -> Path | None:
        if filename not in ALLOWED_FILENAMES:
            return None
        path = self.base_dir / str(check_id) / filename
        return path if path.is_file() else None


async def render_screenshot(
    html_content: str, device: str
) -> bytes | None:
    """Best-effort screenshot of the rendered preview page."""
    if not PLAYWRIGHT_AVAILABLE:
        logger.info("serp preview: Playwright unavailable, skipping screenshot")
        return None
    viewport = MOBILE_VIEWPORT if device == "mobile" else DESKTOP_VIEWPORT
    try:
        pool = BrowserPool.get_instance()
        async with pool.get_page() as page:
            if page is None:
                logger.warning("serp preview: no browser page available")
                return None
            await page.set_viewport_size(viewport)
            await page.set_content(html_content, wait_until="load")
            return await page.screenshot(full_page=True)
    except Exception as exc:
        logger.warning("serp preview: screenshot failed: %s", exc)
        return None


async def save_preview_artifacts(
    check_id: Any, html_content: str, device: str
) -> dict[str, str | None]:
    """Persist the HTML preview and (best-effort) screenshot."""
    storage = PreviewStorage()
    html_url = storage.save_html(check_id, html_content)
    image_url: str | None = None
    png = await render_screenshot(html_content, device)
    if png:
        image_url = storage.save_image(check_id, png)
    return {"html_url": html_url, "image_url": image_url}
