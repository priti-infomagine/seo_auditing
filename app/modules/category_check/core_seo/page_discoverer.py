"""
PageDiscoverer — discovers pages via sitemap and BFS link traversal.

Phase 1: Fetch /robots.txt → extract sitemap URLs → parse sitemaps.
Phase 2: Crawl start page → extract <a href> links → BFS same-domain traversal.
"""
from __future__ import annotations

import re
from collections import deque
from typing import Any
from urllib.parse import urljoin, urlsplit

from .constants import DEFAULT_TIMEOUT
from .models import DiscoveredURL
from .url_normalizer import URLNormalizer
from app.modules.separate_checks.sitemap_check.errors import NoSitemapAvailableError

try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    aiohttp = None  # type: ignore[assignment]


class PageDiscoverer:
    """Discovers pages on a domain via sitemap and BFS link discovery."""

    def __init__(
        self,
        crawler: Any = None,
        config: Any = None,
        http_client: Any = None,
    ):
        self.crawler = crawler
        self.config = config
        self.http_client = http_client

    async def discover_pages(
        self,
        start_url: str,
        max_pages: int = 10,
        max_depth: int = 3,
    ) -> list[DiscoveredURL]:
        """Discover pages starting from *start_url*.

        Args:
            start_url: The seed URL to begin from.
            max_pages: Hard cap on total pages to discover.
            max_depth: Maximum link-hops from the start URL.

        Returns:
            List of DiscoveredURL objects.
        """
        normalized = URLNormalizer.normalize_url(start_url)
        domain = URLNormalizer.get_domain(normalized)

        visited: set[str] = set()
        discovered: list[DiscoveredURL] = []
        queue: deque[tuple[str, int]] = deque()

        if not domain:
            return discovered

        seed_norm = URLNormalizer.normalize_url_canonical(normalized)
        if seed_norm not in visited:
            visited.add(seed_norm)
            queue.append((normalized, 0))
            discovered.append(
                DiscoveredURL(
                    url=normalized,
                    normalized_url=seed_norm,
                    source_type="seed",
                    depth=0,
                )
            )

        sitemap_urls = await self._discover_sitemap_urls(normalized, domain, max_pages)

        # Sitemap-required gate: the Core SEO audit must not proceed unless live
        # discovery found at least one sitemap. Replacing the previous
        # seed-only BFS fallback with a hard abort when no sitemap is present.
        if not sitemap_urls:
            raise NoSitemapAvailableError()

        for url in sitemap_urls:
            if len(discovered) >= max_pages:
                break
            try:
                norm = URLNormalizer.normalize_url_canonical(url)
                if norm not in visited:
                    visited.add(norm)
                    discovered.append(
                        DiscoveredURL(
                            url=url,
                            normalized_url=norm,
                            source_type="sitemap",
                            depth=0,
                        )
                    )
            except (ValueError, Exception):
                continue

        while queue and len(discovered) < max_pages:
            url, depth = queue.popleft()

            if depth >= max_depth:
                continue

            if self.crawler is None:
                html = await self._fetch_html(url)
            else:
                result = await self.crawler.crawl(url)
                html = result.html

            if not html:
                continue

            links = self._extract_links(html, url, domain)
            for link_url, href in links:
                if len(visited) >= max_pages:
                    break
                try:
                    norm = URLNormalizer.normalize_url_canonical(link_url)
                except (ValueError, Exception):
                    continue

                if norm not in visited:
                    visited.add(norm)
                    discovered.append(
                        DiscoveredURL(
                            url=link_url,
                            normalized_url=norm,
                            source_type="html_link",
                            depth=depth + 1,
                        )
                    )
                    queue.append((link_url, depth + 1))

        return discovered[:max_pages]

    async def _discover_sitemap_urls(
        self,
        start_url: str,
        domain: str,
        max_pages: int,
    ) -> list[str]:
        """Fetch robots.txt and sitemap(s), return page URLs from sitemaps."""
        sitemap_urls: list[str] = []

        robots_url = self._build_robots_url(start_url)
        robots_text = await self._fetch_text(robots_url)

        if robots_text:
            sitemap_locs = self._extract_sitemap_locations(robots_text)
            for loc in sitemap_locs[:10]:
                urls = await self._parse_sitemap(loc, max_pages)
                sitemap_urls.extend(urls)

        return sitemap_urls[:max_pages]

    def _build_robots_url(self, start_url: str) -> str:
        try:
            normalized = URLNormalizer.normalize_url(start_url)
            parts = urlsplit(normalized)
            return f"{parts.scheme}://{parts.netloc}/robots.txt"
        except (ValueError, Exception):
            return start_url.rstrip("/") + "/robots.txt"

    async def _fetch_text(self, url: str) -> str:
        """Fetch text content from a URL (robots.txt, sitemap.xml)."""
        if self.http_client is not None:
            return await self.http_client.fetch_text(url)

        if AIOHTTP_AVAILABLE:
            timeout = aiohttp.ClientTimeout(total=DEFAULT_TIMEOUT)
            try:
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.get(url) as response:
                        if response.status == 200:
                            return await response.text()
            except Exception:
                return ""
        return ""

    async def _fetch_html(self, url: str) -> str:
        """Fetch HTML content from a URL (for BFS link discovery)."""
        if self.http_client is not None:
            return await self.http_client.fetch_html(url)

        text = await self._fetch_text(url)
        return text

    def _extract_sitemap_locations(self, robots_text: str) -> list[str]:
        """Extract sitemap URLs from robots.txt content."""
        locations = []
        for line in robots_text.splitlines():
            line = line.strip()
            if line.lower().startswith("sitemap:"):
                loc = line.split(":", 1)[1].strip()
                if loc:
                    locations.append(loc)
        return locations

    async def _parse_sitemap(self, sitemap_url: str, max_pages: int) -> list[str]:
        """Parse a sitemap (XML) and return page URLs."""
        content = await self._fetch_text(sitemap_url)
        if not content:
            return []

        if content.strip().startswith("<?xml") or "<urlset" in content.lower() or "<sitemapindex" in content.lower():
            return self._parse_sitemap_xml(content, sitemap_url, max_pages)

        return [line.strip() for line in content.splitlines() if line.strip()]

    def _parse_sitemap_xml(
        self, content: str, sitemap_url: str, max_pages: int
    ) -> list[str]:
        """Parse XML sitemap and extract URLs (handles sitemap index → nested sitemaps)."""
        urls: list[str] = []
        try:
            soup = BeautifulSoup(content, "xml") if BS4_AVAILABLE else None
        except Exception:
            soup = None

        if soup is not None:
            for loc in soup.find_all("loc"):
                url = loc.get_text().strip()
                if url:
                    urls.append(url)

            for sitemap in soup.find_all("sitemap"):
                loc = sitemap.find("loc")
                if loc:
                    nested_url = loc.get_text().strip()
                    if nested_url:
                        urls.append(nested_url)

        if not urls:
            loc_pattern = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)
            for match in loc_pattern.finditer(content):
                urls.append(match.group(1).strip())

        seen: set[str] = set()
        unique_urls = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique_urls.append(url)
            if len(unique_urls) >= max_pages:
                break

        return unique_urls

    def _extract_links(
        self, html: str, page_url: str, domain: str
    ) -> list[tuple[str, str]]:
        """Extract same-domain links from HTML content.

        Returns list of (resolved_url, original_href) tuples.
        """
        links: list[tuple[str, str]] = []
        try:
            soup = BeautifulSoup(html, "html.parser") if BS4_AVAILABLE else None
        except Exception:
            soup = None

        if soup is not None:
            for anchor in soup.find_all("a", href=True):
                href = str(anchor.get("href", "")).strip()
                if not href:
                    continue
                if href.startswith(("javascript:", "mailto:", "tel:", "data:", "#")):
                    continue

                resolved = urljoin(page_url, href)

                try:
                    target_domain = URLNormalizer.get_domain(resolved)
                except (ValueError, Exception):
                    continue

                if target_domain and URLNormalizer.is_same_site(domain, target_domain):
                    links.append((resolved, href))

        return links


try:
    from bs4 import BeautifulSoup

    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False
    BeautifulSoup = None  # type: ignore[assignment]


__all__ = ["PageDiscoverer"]
