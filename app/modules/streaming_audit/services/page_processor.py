from __future__ import annotations

import time
from typing import Any
from urllib.parse import urljoin, urlsplit

from app.modules.streaming_audit.adapters.crawler_adapter import CrawlerAdapter
from app.modules.streaming_audit.adapters.parser_adapter import ParserAdapter
from app.modules.streaming_audit.adapters.rule_engine_adapter import RuleEngineAdapter


class PageProcessor:
    """Single page processing lifecycle for the streaming audit experiment."""

    def __init__(self, crawler_adapter: CrawlerAdapter | None = None, parser_adapter: ParserAdapter | None = None,
                 rule_engine_adapter: RuleEngineAdapter | None = None):
        self.crawler_adapter = crawler_adapter or CrawlerAdapter()
        self.parser_adapter = parser_adapter or ParserAdapter()
        self.rule_engine_adapter = rule_engine_adapter or RuleEngineAdapter()

    async def process_page(self, audit_id: str, url: str, depth: int = 0) -> dict[str, Any]:
        started = time.perf_counter()
        fetch_result = await self.crawler_adapter.fetch_page(url)
        if fetch_result["status"] != "ok":
            return {
                "audit_id": audit_id,
                "url": url,
                "normalized_url": fetch_result["final_url"] or url,
                "status": "failed",
                "error": fetch_result.get("error") or "page fetch failed",
                "http_status": fetch_result.get("status_code"),
                "page_score": 0,
                "discovered_urls": [],
                "processing_latency_ms": int((time.perf_counter() - started) * 1000),
            }

        base_url = fetch_result.get("final_url") or url
        parsed_data = self.parser_adapter.parse_html(fetch_result["html"], base_url, fetch_result)
        rule_result = await self.rule_engine_adapter.evaluate(parsed_data)

        discovered_urls: list[str] = []
        for link in parsed_data.get("links", []) or []:
            href = link.get("href") if isinstance(link, dict) else None
            if not isinstance(href, str) or not href.strip():
                continue
            resolved_url = urljoin(base_url, href.strip())
            parts = urlsplit(resolved_url)
            if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
                continue
            discovered_urls.append(resolved_url)

        return {
            "audit_id": audit_id,
            "url": url,
            "normalized_url": fetch_result["final_url"] or url,
            "canonical_url": fetch_result["final_url"] or url,
            "status": "completed",
            "http_status": fetch_result.get("status_code"),
            "page_score": rule_result.get("overall_score", 0),
            "passed_checks": rule_result.get("passed_checks", 0),
            "failed_checks": rule_result.get("failed_checks", 0),
            "warnings": rule_result.get("warnings", []),
            "issues": rule_result.get("issues", []),
            "rule_results": rule_result.get("rule_results", []),
            "discovered_urls": discovered_urls,
            "parsed_payload": parsed_data,
            "processing_latency_ms": int((time.perf_counter() - started) * 1000),
            "depth": depth,
        }
