"""
HTTP Client utility for making web requests.
"""
from typing import Optional

import httpx


async def fetch_url(
    url: str,
    timeout: int = 30,
    follow_redirects: bool = True,
    user_agent: Optional[str] = None,
) -> httpx.Response:
    """
    Fetch a URL and return the raw HTTP response.
    
    Args:
        url: The URL to fetch
        timeout: Request timeout in seconds
        follow_redirects: Whether to follow redirects
        user_agent: Optional user agent string
        
    Returns:
        Raw httpx.Response object
    """
    headers = {}
    if user_agent:
        headers["User-Agent"] = user_agent
    
    async with httpx.AsyncClient(
        follow_redirects=follow_redirects,
        timeout=timeout,
    ) as client:
        response = await client.get(url, headers=headers)
        return response