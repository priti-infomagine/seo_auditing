"""
CrawlerService - high-level crawler service.

Wraps ``WebCrawler`` to crawl a single URL and persist the results
to disk in ``app/storage/crawler/<domain>/``.  Returns a dict that
the API layer and tests expect.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from app.modules.crawler.services.crawler import CrawlResult, WebCrawler
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

    def __init__(self, web_crawler: Optional[WebCrawler] = None):
        self.crawler = web_crawler or WebCrawler()

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
        result: CrawlResult = await self.crawler.crawl(normalized)

        # Determine incremental test number for this domain
        test_number = self._get_next_test_number(domain)

        # Build storage path and ensure the directory exists
        storage_path = self._get_storage_path(domain, test_number)
        storage_path.parent.mkdir(parents=True, exist_ok=True)

        # Save full crawl data to disk
        self._save_to_storage(result, storage_path, normalized, domain, test_number)

        crawled_at = datetime.now(timezone.utc).isoformat()

        # Build the response ``data`` dict -- includes convenience keys
        # (status_code, response_time, html_size) expected by the API
        # tests, plus the full sub-dicts that score.py feeds to the parser.
        data = result.to_dict()
        data["status_code"] = result.http["status_code"]
        data["response_time"] = result.http["response_time"]
        data["html_size"] = result.http["content_size"]

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
        result: CrawlResult,
        storage_path: Path,
        requested_url: str,
        domain: str,
        test_number: int,
    ) -> None:
        """Write the crawl result to a JSON file on disk."""
        payload = result.to_dict()
        payload["domain"] = domain
        payload["test_number"] = test_number
        payload["crawled_at"] = datetime.now(timezone.utc).isoformat()

        with open(storage_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
