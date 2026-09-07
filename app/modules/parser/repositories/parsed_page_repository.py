from __future__ import annotations

from typing import Any


class ParsedPageRepository:
    """
    Persistence abstraction for ParsedPage objects.

    Implementations may write to PostgreSQL, filesystem, or object storage.
    """

    async def save(self, parsed_page: Any) -> None:
        raise NotImplementedError

    async def bulk_save(self, parsed_pages: list[Any]) -> None:
        raise NotImplementedError

    async def get_by_crawl_id(self, crawl_id: str) -> Any | None:
        raise NotImplementedError

    async def get_by_page_id(self, page_id: str) -> Any | None:
        raise NotImplementedError

    async def update(self, parsed_page: Any) -> None:
        raise NotImplementedError

    async def delete(self, parsed_page_id: str) -> None:
        raise NotImplementedError
