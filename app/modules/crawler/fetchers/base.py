"""
Fetcher protocol abstraction.
"""
from typing import Dict, Optional, Protocol, runtime_checkable

from app.modules.crawler.types import FetchResult


@runtime_checkable
class Fetcher(Protocol):
    """Abstraction for fetching web pages via HTTP or Browser rendering."""

    async def fetch(
        self,
        url: str,
        *,
        timeout: float = 30.0,
        headers: Optional[Dict[str, str]] = None,
    ) -> FetchResult:
        """Fetch a single URL and return a normalized FetchResult."""
        ...
