
"""
Generic asynchronous HTTP client utility.

Responsibilities:
- Manage a reusable HTTPX client
- Perform HTTP GET requests
- Configure timeout and redirects
- Configure default User-Agent

This module is intentionally unaware of:
- SEO
- crawling rules
- parsing
- extraction
- retries
- persistence
"""

from typing import Optional

import httpx


class HTTPClient:
    """
    Reusable asynchronous HTTP client.

    A single instance should be reused during a crawl so HTTPX
    can maintain connection pools and reuse TCP/TLS connections.
    """

    def __init__(
        self,
        timeout: float = 30.0,
        follow_redirects: bool = True,
        max_redirects: int = 10,
        user_agent: Optional[str] = None,
    ) -> None:
        headers: dict[str, str] = {}

        if user_agent:
            headers["User-Agent"] = user_agent

        self._client = httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=follow_redirects,
            max_redirects=max_redirects if follow_redirects else 0,
            headers=headers,
        )

    async def get(self, url: str) -> httpx.Response:
        """
        Perform an HTTP GET request.

        Returns the raw HTTPX response.
        """
        return await self._client.get(url)

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "HTTPClient":
        return self

    async def __aexit__(
        self,
        exc_type,
        exc_value,
        traceback,
    ) -> None:
        await self.close()


