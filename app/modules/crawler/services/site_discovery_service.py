"""
Site discovery service - discovers robots.txt, sitemaps, and site-level data.

This service:
1. Fetches robots.txt
2. Fetches sitemap.xml / sitemap index
3. Extracts sitemap URLs
4. Returns raw evidence

It does NOT:
- Write to PostgreSQL
- Score robots/sitemap compliance
"""
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.shared.utils.http_client import HTTPClient
from app.shared.utils.url_utils import get_domain


@dataclass
class RobotsTxtEvidence:
    """Raw evidence from robots.txt."""
    url: str = ""
    exists: bool = False
    status_code: Optional[int] = None
    content: Optional[str] = None
    rules_count: int = 0
    allows_crawling: bool = True
    sitemap_references: list = field(default_factory=list)


@dataclass
class SitemapEvidence:
    """Raw evidence from sitemap."""
    url: str = ""
    exists: bool = False
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    content_length: int = 0
    urls: list = field(default_factory=list)


@dataclass
class SiteDiscoveryResult:
    """Combined site discovery result."""
    robots: RobotsTxtEvidence
    sitemaps: list = field(default_factory=list)
    discovered_urls: list = field(default_factory=list)


class SiteDiscoveryService:
    """Service for site-level discovery."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout
        parsed = urlparse(base_url)
        self.scheme = parsed.scheme
        self.domain = get_domain(base_url)

    async def discover(self) -> SiteDiscoveryResult:
        """
        Discover robots.txt and sitemaps for a site.

        Returns:
            SiteDiscoveryResult with raw evidence
        """
        robots = await self._fetch_robots()
        sitemaps = await self._discover_sitemaps(robots)

        discovered_urls = []
        for sitemap in sitemaps:
            discovered_urls.extend(sitemap.urls[:100])

        return SiteDiscoveryResult(
            robots=robots,
            sitemaps=sitemaps,
            discovered_urls=discovered_urls,
        )

    async def _fetch_robots(self) -> RobotsTxtEvidence:
        """Fetch and inspect robots.txt."""
        robots_url = f"{self.scheme}://{self.domain}/robots.txt"
        evidence = RobotsTxtEvidence(url=robots_url)

        try:
            async with HTTPClient(robots_url, timeout=self.timeout) as response:
                evidence.status_code = response.status_code
                if response.status_code == 200:
                    evidence.exists = True
                    evidence.content = response.text
                    lines = [
                        ln.strip()
                        for ln in response.text.splitlines()
                        if ln.strip() and not ln.strip().startswith("#")
                    ]
                    evidence.rules_count = len(lines)
                    evidence.allows_crawling = not bool(
                        __import__("re").search(
                            r"disallow:\s*/\s*$",
                            response.text,
                            __import__("re").IGNORECASE | __import__("re").MULTILINE,
                        )
                    )

                    import re
                    for line in response.text.splitlines():
                        match = re.match(r"sitemap:\s*(\S+)", line, re.IGNORECASE)
                        if match:
                            evidence.sitemap_references.append(match.group(1))
        except Exception:
            pass

        return evidence

    async def _discover_sitemaps(self, robots: RobotsTxtEvidence) -> list:
        """Discover sitemaps from robots.txt references and common locations."""
        sitemap_candidates = list(robots.sitemap_references)
        common_paths = ["/sitemap.xml", "/sitemap_index.xml", "/sitemap/"]
        for path in common_paths:
            sitemap_candidates.append(f"{self.scheme}://{self.domain}{path}")

        sitemaps = []
        seen = set()
        for sitemap_url in sitemap_candidates:
            if sitemap_url in seen:
                continue
            seen.add(sitemap_url)

            evidence = await self._fetch_sitemap(sitemap_url)
            if evidence.exists:
                sitemaps.append(evidence)

        return sitemaps

    async def _fetch_sitemap(self, sitemap_url: str) -> SitemapEvidence:
        """Fetch a sitemap and extract URLs."""
        evidence = SitemapEvidence(url=sitemap_url)

        try:
            async with HTTPClient(sitemap_url, timeout=self.timeout) as response:
                evidence.status_code = response.status_code
                evidence.content_type = response.headers.get("content-type", "")
                evidence.content_length = len(response.content)

                if response.status_code == 200 and response.content:
                    evidence.exists = True
                    try:
                        import xml.etree.ElementTree as ET
                        root = ET.fromstring(response.content)
                        for url_elem in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}url"):
                            loc = url_elem.find("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                            if loc is not None and loc.text:
                                evidence.urls.append(loc.text.strip())
                    except Exception:
                        pass
        except Exception:
            pass

        return evidence
