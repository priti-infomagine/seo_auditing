"""
Full-site diagnostic: crawls every discoverable internal page of a site via
httpx AND via Playwright, extracts SEO facts from both for each page, and
reports where they diverge.

Reuses your existing pipeline components (HttpFetcher, BrowserFetcher,
RenderDetector, DocumentParserService, LinkExtractor, url_utils). Does NOT
touch protected files, does NOT write to the database, does NOT use
CrawlOrchestrator/CrawlScheduler — this is a standalone, read-only BFS.

Usage (from backend/ root):
    python diagnose_site_gap.py https://kanhahometutions.com
    python diagnose_site_gap.py https://kanhahometutions.com --max-pages 30
    python diagnose_site_gap.py https://kanhahometutions.com --max-pages 30 --csv report.csv

Notes:
- This is a diagnostic, not a load test. Default max_pages=25 and
  concurrency=3 are intentionally conservative so you don't hammer a live
  site. Raise them only on sites you own or have permission to crawl.
- Respects nothing except same-domain filtering — it does NOT check
  robots.txt. Only point this at sites you're authorized to crawl.
"""
import argparse
import asyncio
import csv
import sys
import time
from collections import deque
from typing import Optional

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

from app.modules.crawler.fetchers.http_fetcher import HttpFetcher
from app.modules.crawler.fetchers.browser_fetcher import BrowserFetcher
from app.modules.crawler.rendering.render_detector import RenderDetector
from app.modules.crawler.config import CrawlConfig
from app.modules.parser.services.document_parser_service import DocumentParserService
from app.modules.parser.extractors.link_extractor import LinkExtractor
from app.shared.utils.url_utils import normalize_url, get_domain, is_internal_link


FACT_KEYS = ["title", "meta_description", "canonical", "h1_count", "h1_text", "json_ld_blocks"]


def extract_key_facts(html: str, url: str) -> dict:
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
        "h1_text": tuple(h.get_text(strip=True) for h in h1s[:3]),
        "json_ld_blocks": len(ldjson),
    }


def extract_internal_links(html: str, page_url: str, base_domain: str) -> set:
    ctx = DocumentParserService().parse(html, page_url)
    links = LinkExtractor().extract(ctx)
    found = set()
    for link in links:
        abs_url = link.absolute_url
        if not abs_url or not abs_url.startswith(("http://", "https://")):
            continue
        if not is_internal_link(page_url, abs_url):
            continue
        try:
            norm = normalize_url(abs_url)
        except Exception:
            continue
        # Strip fragments; keep query strings (some sites route on query params)
        norm = norm.split("#", 1)[0]
        if get_domain(norm) == base_domain:
            found.add(norm)
    return found


async def crawl_via(fetch_fn, start_url: str, max_pages: int, concurrency: int, label: str) -> dict:
    """
    Simple BFS same-domain crawl using the given fetch_fn (either the http
    fetcher's .fetch or the browser fetcher's .fetch). Returns
    {normalized_url: {"facts": {...}, "success": bool, "error": str|None}}
    """
    base_domain = get_domain(start_url)
    seen = {normalize_url(start_url)}
    queue = deque([normalize_url(start_url)])
    results = {}
    sem = asyncio.Semaphore(concurrency)

    async def worker(url: str):
        async with sem:
            try:
                # Hard ceiling independent of the fetcher's internal timeout,
                # so one pathological page can't silently stall the whole
                # batch (e.g. a page that never reaches networkidle and
                # rides the full browser_timeout every single time).
                fetch_result = await asyncio.wait_for(
                    fetch_fn(url, timeout=30), timeout=50
                )
            except asyncio.TimeoutError:
                print(f"  [{label}] TIMEOUT (>50s) on {url} - skipping")
                results[url] = {"facts": None, "success": False, "error": "diagnostic_hard_timeout"}
                return set()
            except Exception as exc:
                results[url] = {"facts": None, "success": False, "error": repr(exc)}
                return set()

            if not fetch_result.success:
                results[url] = {
                    "facts": None,
                    "success": False,
                    "error": f"{fetch_result.error} ({fetch_result.error_type})",
                }
                return set()

            html = fetch_result.content.decode("utf-8", errors="replace")
            facts = extract_key_facts(html, url)
            results[url] = {"facts": facts, "success": True, "error": None}

            try:
                return extract_internal_links(html, url, base_domain)
            except Exception:
                return set()

    print(f"\n[{label}] Starting BFS crawl (max_pages={max_pages}, concurrency={concurrency})...")
    t0 = time.perf_counter()

    while queue and len(results) < max_pages:
        batch = []
        while queue and len(batch) < concurrency and (len(results) + len(batch)) < max_pages:
            batch.append(queue.popleft())

        if batch:
            print(f"  [{label}] batch starting ({len(batch)} pages): {', '.join(batch)}")

        batch_link_sets = await asyncio.gather(*(worker(u) for u in batch))

        for link_set in batch_link_sets:
            for link in link_set:
                if link not in seen and len(seen) < max_pages:
                    seen.add(link)
                    queue.append(link)

        print(f"  [{label}] crawled={len(results)} queued={len(queue)} elapsed={time.perf_counter()-t0:.1f}s")

    print(f"[{label}] Done. {len(results)} pages in {time.perf_counter()-t0:.1f}s")
    return results


async def main():
    parser = argparse.ArgumentParser(description="Compare httpx vs Playwright across an entire site.")
    parser.add_argument("url", help="Start URL, e.g. https://example.com")
    parser.add_argument("--max-pages", type=int, default=25, help="Max pages to crawl per fetcher (default 25)")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent requests per fetcher (default 3)")
    parser.add_argument("--csv", type=str, default=None, help="Optional path to write a CSV report")
    args = parser.parse_args()

    config = CrawlConfig()
    http_fetcher = HttpFetcher(config=config)
    browser_fetcher = BrowserFetcher(config=config)
    detector = RenderDetector()

    http_results = await crawl_via(
        http_fetcher.fetch, args.url, args.max_pages, args.concurrency, "httpx"
    )
    browser_results = await crawl_via(
        browser_fetcher.fetch, args.url, args.max_pages, args.concurrency, "playwright"
    )

    all_urls = sorted(set(http_results.keys()) | set(browser_results.keys()))

    print(f"\n{'='*90}")
    print(f"SITE COMPARISON: {args.url}")
    print(f"httpx pages crawled: {len(http_results)}  |  playwright pages crawled: {len(browser_results)}")
    print(f"{'='*90}")

    rows = []
    divergent_count = 0
    httpx_only_fail = 0
    both_fail = 0

    for url in all_urls:
        h = http_results.get(url)
        b = browser_results.get(url)

        row = {"url": url}

        if h is None:
            row["status"] = "not_reached_by_httpx"
        elif b is None:
            row["status"] = "not_reached_by_playwright"
        elif not h["success"] and not b["success"]:
            row["status"] = "both_failed"
            both_fail += 1
        elif not h["success"]:
            row["status"] = "httpx_failed_playwright_ok"
            httpx_only_fail += 1
        elif not b["success"]:
            row["status"] = "playwright_failed_httpx_ok"
        else:
            diffs = [k for k in FACT_KEYS if h["facts"].get(k) != b["facts"].get(k)]
            if diffs:
                row["status"] = "diverges: " + ",".join(diffs)
                divergent_count += 1
            else:
                row["status"] = "match"

        row["httpx_error"] = h["error"] if h else None
        row["playwright_error"] = b["error"] if b else None
        rows.append(row)

        marker = "  " if row["status"] == "match" else "->"
        print(f"{marker} {url}\n     {row['status']}")

    print(f"\n{'-'*90}")
    print("SUMMARY")
    print(f"  Total unique pages seen:      {len(all_urls)}")
    print(f"  Matching (no divergence):     {len(all_urls) - divergent_count - both_fail - httpx_only_fail}")
    print(f"  Diverging SEO facts:          {divergent_count}")
    print(f"  httpx failed but PW succeeded:{httpx_only_fail}  <-- pages RenderDetector likely mis-scored if never rendered")
    print(f"  Both failed:                  {both_fail}")
    print(f"{'-'*90}")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["url", "status", "httpx_error", "playwright_error"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nCSV report written to: {args.csv}")

    await asyncio.sleep(0.25)  # let Playwright subprocess transports close cleanly on Windows


if __name__ == "__main__":
    asyncio.run(main())