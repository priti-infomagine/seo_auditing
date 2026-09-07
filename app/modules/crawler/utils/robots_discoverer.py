"""
RobotsDiscoverer - Fetches and parses robots.txt for a site domain.
"""
from typing import List, Optional
from urllib.parse import urlparse

from app.modules.crawler.services.robots_service import RobotsService, RobotsPolicy


class RobotsDiscoverer:
    """Fetches robots.txt and evaluates crawl permissions."""

    def __init__(self, user_agent: str = "*"):
        self.service = RobotsService(user_agent=user_agent)

    async def fetch_policy(self, start_url: str, timeout: float = 10.0) -> Optional[RobotsPolicy]:
        try:
            return await self.service.fetch_policy(start_url, timeout=timeout)
        except Exception:
            return None

    def is_allowed(self, url: str, policy: RobotsPolicy) -> bool:
        try:
            return self.service.is_allowed(url, policy)
        except Exception:
            return True
