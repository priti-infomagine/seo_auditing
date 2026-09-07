"""
Standalone diagnostic: compares httpx fetch vs Playwright render for one URL,
using your existing HttpFetcher / BrowserFetcher / RenderDetector / DocumentParserService.

Run from backend/ root:
    python diagnose_render_gap.py https://kanhahonetutions.com

This does NOT modify any protected file. It only imports and calls them.
"""
import asyncio
import sys

if sys.platform == "win32":
    # Same reasoning as app/main.py: Playwright's async API launches Chromium
    # as a subprocess, which Windows' default Selector loop cannot do.
    # Proactor is required. This script is standalone and does not import
    # app/main.py, so it must set this itself.
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.modules.crawler.fetchers.http_fetcher import HttpFetcher
from app.modules.crawler.fetchers.browser_fetcher import BrowserFetcher
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.config import CrawlConfig
from app.modules.parser.services.document_parser_service import DocumentParserService


KEY_TAGS = ["title", "meta[name=description]", "link[rel=canonical]", "h1", "script[type='application/ld+json']"]


def extract_key_facts(html: str, url: str):
    ctx = DocumentParserService().parse(html, url)
    soup = ctx.soup
    title = soup.find("title")
    meta_desc = soup.find("meta", attrs={"name": "description"})
    canonical = soup.find("link", attrs={"rel": "canonical"})
    h1s = soup.find_all("h1")
    ldjson = soup.find_all("script", attrs={"type": "application/ld+json"})
    return {
        "title": title.get_text(strip=True) if title else None,
        "meta_description": meta_desc.get("content") if meta_desc else None,
        "canonical": canonical.get("href") if canonical else None,
        "h1_count": len(h1s),
        "h1_text": [h.get_text(strip=True) for h in h1s[:3]],
        "json_ld_blocks": len(ldjson),
        "html_length": len(html),
    }


async def main(url: str):
    config = CrawlConfig()
    http_fetcher = HttpFetcher(config=config)
    browser_fetcher = BrowserFetcher(config=config)
    detector = RenderDetector()

    print(f"\n=== Fetching via httpx: {url} ===")
    http_result = await http_fetcher.fetch(url, timeout=config.request_timeout)
    print(f"status={http_result.status_code} success={http_result.success} "
          f"final_url={http_result.final_url} content_len={len(http_result.content)}")

    if not http_result.success:
        print(f"HTTP fetch FAILED: {http_result.error} ({http_result.error_type})")
        return

    html_http = http_result.content.decode("utf-8", errors="replace")
    decision = detector.evaluate(http_result)
    print(f"\nRenderDetector decision: needs_render={decision.needs_render} reason={decision.reason} details={decision.details}")

    facts_http = extract_key_facts(html_http, url)
    print("\n--- httpx-extracted SEO facts ---")
    for k, v in facts_http.items():
        print(f"  {k}: {v}")

    print(f"\n=== Fetching via Playwright (forced, regardless of detector) ===")
    browser_result = await browser_fetcher.fetch(url, timeout=config.browser_timeout)
    print(f"status={browser_result.status_code} success={browser_result.success} "
          f"final_url={browser_result.final_url} content_len={len(browser_result.content)}")

    if not browser_result.success:
        print(f"Browser fetch FAILED: {browser_result.error} ({browser_result.error_type})")
        return

    html_browser = browser_result.content.decode("utf-8", errors="replace")
    facts_browser = extract_key_facts(html_browser, url)
    print("\n--- Playwright-extracted SEO facts ---")
    for k, v in facts_browser.items():
        print(f"  {k}: {v}")

    print("\n=== DIFF (httpx vs Playwright) ===")
    any_diff = False
    for k in facts_http:
        if facts_http[k] != facts_browser[k]:
            any_diff = True
            print(f"  DIVERGES on '{k}':")
            print(f"    httpx:      {facts_http[k]}")
            print(f"    playwright: {facts_browser[k]}")

    if http_result.final_url != browser_result.final_url:
        any_diff = True
        print(f"  DIVERGES on final_url:")
        print(f"    httpx:      {http_result.final_url}")
        print(f"    playwright: {browser_result.final_url}")

    if not any_diff:
        print("  No divergence detected on key SEO facts.")

    if not decision.needs_render and any_diff:
        print("\n*** RenderDetector said 'no render needed' but facts DIVERGED. ***")
        print("*** This page currently gets scored using ONLY the httpx (possibly wrong) facts. ***")


async def _run_and_settle(url: str):
    await main(url)
    # Let Playwright's Chromium subprocess transport finish closing its
    # pipes before asyncio.run() tears the loop down. Without this, Windows
    # fires BaseSubprocessTransport.__del__ after the loop is already closed,
    # producing a harmless but noisy "Event loop is closed" traceback.
    await asyncio.sleep(0.25)


if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "https://kanhahonetutions.com"
    asyncio.run(_run_and_settle(target_url))