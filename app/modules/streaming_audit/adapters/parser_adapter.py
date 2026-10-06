from __future__ import annotations

from typing import Any

from app.modules.parser.services.parser_orchestrator import ParserOrchestrator


class ParserAdapter:
    """Thin adapter over the existing parser service."""

    def __init__(self):
        self.parser = ParserOrchestrator()

    def parse_html(self, html: str, url: str, fetch_result: dict[str, Any] | None = None) -> dict[str, Any]:
        crawler_data = {
            "requested_url": url,
            "final_url": fetch_result.get("final_url", url) if fetch_result else url,
            "status_code": fetch_result.get("status_code") if fetch_result else None,
            "content_type": fetch_result.get("content_type") if fetch_result else None,
            "response_time_ms": fetch_result.get("response_time_ms") if fetch_result else None,
            "headers": {},
            "redirect_chain": fetch_result.get("redirect_chain", []) if fetch_result else [],
        }
        return self.parser.parse_html(html, url, crawler_data=crawler_data)
