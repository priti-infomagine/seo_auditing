from __future__ import annotations

from typing import Any


class ParserRepository:
    """
    Repository for parser-level metadata and batch tracking.
    """

    async def record_parse(self, crawl_id: str, parsed_page_id: str, data: dict[str, Any]) -> None:
        raise NotImplementedError

    async def get_parse_history(self, crawl_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError
