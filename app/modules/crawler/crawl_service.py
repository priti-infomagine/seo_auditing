"""
CrawlerService - high-level crawler service.

Wraps the new crawler services to crawl a single URL and persist the results
to disk in ``app/storage/crawler/<domain>/``.  Returns a dict that
the API layer and tests expect.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.modules.crawler.services.page_crawl_service import PageCrawlService, PageCrawlResult
from app.shared.utils.url_utils import get_domain, normalize_url

# Project root is three levels above this file:
#   app/services/crawler/crawl_service.py -> app/ -> backend root
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_STORAGE_DIR = _PROJECT_ROOT / "app" / "storage" / "crawler"


class CrawlerService:
    """
    Service that crawls a URL, saves the result to storage,
    and returns a structured response dict.
    """

    def __init__(self, page_crawl_service: Optional[PageCrawlService] = None):
        self.page_crawl_service = page_crawl_service or PageCrawlService()

    async def crawl_url(self, url: str) -> dict:
        """
        Crawl a single URL, save results to storage, and return a
        structured dict.

        Args:
            url: URL to crawl (with or without protocol).

        Returns:
            Dict with keys: url, domain, test_number, file_path,
            crawled_at, data.

        Raises:
            ValueError: if the URL is invalid.
            RuntimeError: if the crawl fails.
        """
        # Normalise / validate
        normalized = normalize_url(url)
        domain = get_domain(normalized)
        if not domain:
            raise ValueError(f"Invalid URL: {url} - could not extract domain")

        # Crawl
        result: PageCrawlResult = await self.page_crawl_service.crawl_page(normalized)

        if result.error:
            raise RuntimeError(f"Crawl failed for {normalized}: {result.error}")

        # Determine incremental test number for this domain
        test_number = self._get_next_test_number(domain)

        # Build storage path and ensure the directory exists
        storage_path = self._get_storage_path(domain, test_number)
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Save full crawl data to disk
        self._save_to_storage(result, storage_path, normalized, domain, test_number)

        crawled_at = datetime.now(timezone.utc).isoformat()

        # Build the response ``data`` dict
        data = {
            "requested_url": result.url,
            "final_url": result.fetch_result.final_url if result.fetch_result else result.url,
            "html": result.document.raw_html if result.document else "",
            "http": {
                "status_code": result.fetch_result.status_code if result.fetch_result else 0,
                "response_time": (result.fetch_result.response_time_ms / 1000.0) if result.fetch_result else 0,
                "response_time_ms": result.fetch_result.response_time_ms if result.fetch_result else 0,
                "content_type": result.fetch_result.content_type if result.fetch_result else "",
                "content_size": result.fetch_result.content_length if result.fetch_result else 0,
                "headers": result.fetch_result.headers if result.fetch_result else {},
            },
        }
        data["status_code"] = data["http"]["status_code"]
        data["response_time"] = data["http"]["response_time"]
        data["html_size"] = data["http"]["content_size"]

        return {
            "url": normalized,
            "domain": domain,
            "test_number": test_number,
            "file_path": str(storage_path),
            "crawled_at": crawled_at,
            "data": data,
        }

    # -- private helpers ------------------------------------------------

    def _get_next_test_number(self, domain: str) -> int:
        """Find the next incremental test number for a domain."""
        domain_dir = _STORAGE_DIR / domain
        if not domain_dir.exists():
            return 1
        existing = sorted(domain_dir.glob(f"{domain}_test_*.json"))
        if not existing:
            return 1
        max_num = 0
        for f in existing:
            name = f.stem
            parts = name.rsplit("_test_", 1)
            if len(parts) == 2:
                try:
                    max_num = max(max_num, int(parts[1]))
                except ValueError:
                    continue
        return max_num + 1

    def _get_storage_path(self, domain: str, test_number: int) -> Path:
        """Build the storage file path for a given domain + test number."""
        filename = f"{domain}_test_{test_number}.json"
        return _STORAGE_DIR / domain / filename

    def _save_to_storage(
        self,
        result: PageCrawlResult,
        storage_path: Path,
        requested_url: str,
        domain: str,
        test_number: int,
    ) -> None:
        """Write the crawl result to a JSON file on disk."""
        payload = {
            "requested_url": result.url,
            "final_url": result.fetch_result.final_url if result.fetch_result else result.url,
            "html": result.document.raw_html if result.document else "",
            "http": {
                "status_code": result.fetch_result.status_code if result.fetch_result else 0,
                "response_time": (result.fetch_result.response_time_ms / 1000.0) if result.fetch_result else 0,
                "response_time_ms": result.fetch_result.response_time_ms if result.fetch_result else 0,
                "content_type": result.fetch_result.content_type if result.fetch_result else "",
                "content_size": result.fetch_result.content_length if result.fetch_result else 0,
                "headers": result.fetch_result.headers if result.fetch_result else {},
            },
        }
        payload["domain"] = domain
        payload["test_number"] = test_number
        payload["crawled_at"] = datetime.now(timezone.utc).isoformat()

        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
