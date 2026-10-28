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
        preflight_sitemap_urls: list[str] | None = None,
    ) -> list[DiscoveredURL]:
        """Discover pages starting from *start_url*.

        Args:
            start_url: The seed URL to begin from.
            max_pages: Hard cap on total pages to discover.
            max_depth: Maximum link-hops from the start URL.
            preflight_sitemap_urls: Pre-discovered sitemap page URLs from a
                pre-flight check (HTTP level). When provided, the sitemap
                fetch + parse steps are skipped entirely, avoiding redundant
                network requests inside the celery worker.

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

        sitemap_urls = (
            preflight_sitemap_urls
            if preflight_sitemap_urls is not None
            else await self._discover_sitemap_urls(normalized, domain, max_pages)
        )

        # No sitemap? Fall through to BFS link discovery from the seed URL
        # (already queued above). This allows auditing sites that don't expose a
        # sitemap.xml while still preferring sitemap URLs when available.

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
        """Fetch robots.txt and sitemap(s), return page URLs from sitemaps.

        Sitemaps are discovered from two sources:
        1. ``Sitemap:`` directives in robots.txt
        2. Common sitemap paths (/sitemap.xml, /wp-sitemap.xml, etc.)

        Sitemap-index files are recursively expanded to fetch their child
        sitemaps before extracting page URLs.
        """
        sitemap_urls: list[str] = []

        robots_url = self._build_robots_url(start_url)
        robots_text = await self._fetch_text(robots_url)

        sitemap_candidates: list[str] = []
        if robots_text:
            sitemap_candidates.extend(
                self._extract_sitemap_locations(robots_text)
            )

        # Probe common sitemap locations — many sites publish a sitemap without
        # referencing it in robots.txt. Mirrors SiteDiscoveryService behavior.
        parts = urlsplit(start_url)
        base = f"{parts.scheme}://{parts.netloc}"
        common_paths = [
            "/sitemap.xml",
            "/sitemap_index.xml",
            "/sitemap-index.xml",
            "/sitemap/",
            "/wp-sitemap.xml",
            "/posts/sitemap.xml",
            "/pages/sitemap.xml",
            "/sitemap-posts.xml",
            "/sitemap-pages.xml",
        ]
        for path in common_paths:
            url = urljoin(base, path)
            if url not in sitemap_candidates:
                sitemap_candidates.append(url)

        seen: set[str] = set()
        for sitemap_url in sitemap_candidates[:20]:
            if sitemap_url in seen:
                continue
            seen.add(sitemap_url)

            if len(sitemap_urls) >= max_pages:
                break

            urls, child_sitemaps = await self._parse_sitemap_with_children(
                sitemap_url, max_pages
            )
            sitemap_urls.extend(urls)

            # Recursively expand child sitemaps from sitemap-index files
            for child_url in child_sitemaps:
                if child_url in seen:
                    continue
                seen.add(child_url)
                if len(sitemap_urls) >= max_pages:
                    break
                child_urls, _ = await self._parse_sitemap_with_children(
                    child_url, max_pages
                )
                sitemap_urls.extend(child_urls)

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

        # Fallback: httpx (aiohttp not installed)
        try:
            import httpx

            async with httpx.AsyncClient(
                timeout=DEFAULT_TIMEOUT, follow_redirects=True
            ) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.text
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

    async def _parse_sitemap_with_children(
        self, sitemap_url: str, max_pages: int
    ) -> tuple[list[str], list[str]]:
        """Fetch and parse a sitemap, returning (page_urls, child_sitemap_urls).

        Page URLs come from ``<url><loc>`` entries; child sitemap URLs come from
        ``<sitemap><loc>`` entries (sitemap-index files). The caller is
        responsible for recursively expanding child sitemaps.
        """
        content = await self._fetch_text(sitemap_url)
        if not content:
            return [], []

        if (
            content.strip().startswith("<?xml")
            or "<urlset" in content.lower()
            or "<sitemapindex" in content.lower()
        ):
            return self._parse_sitemap_xml(content, sitemap_url, max_pages)

        # Non-XML: treat each non-empty line as a URL
        urls = [line.strip() for line in content.splitlines() if line.strip()]
        return urls[:max_pages], []

    def _parse_sitemap_xml(
        self, content: str, sitemap_url: str, max_pages: int
    ) -> tuple[list[str], list[str]]:
        """Parse XML sitemap and extract page URLs and child sitemap references.

        Returns ``(page_urls, child_sitemap_urls)`` so the caller can
        recursively expand sitemap-index files.
        """
        page_urls: list[str] = []
        child_sitemaps: list[str] = []
        try:
            soup = BeautifulSoup(content, "xml") if BS4_AVAILABLE else None
        except Exception:
            soup = None

        if soup is not None:
            # Page URLs live in <url><loc>...</loc></url>
            for loc in soup.find_all("loc"):
                # Skip <loc> that are children of <sitemap> (those are child sitemaps)
                parent = loc.parent
                if parent is not None and parent.name == "sitemap":
                    continue
                url = loc.get_text().strip()
                if url:
                    page_urls.append(url)

            # Child sitemap references live in <sitemap><loc>...</loc></sitemap>
            for sitemap in soup.find_all("sitemap"):
                loc = sitemap.find("loc")
                if loc:
                    nested_url = loc.get_text().strip()
                    if nested_url:
                        child_sitemaps.append(nested_url)

        # Fallback: regex extraction if BeautifulSoup is unavailable or found nothing
        if not page_urls and not child_sitemaps:
            loc_pattern = re.compile(
                r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL
            )
            urlset_context = re.compile(
                r"<urlset.*?</urlset>", re.IGNORECASE | re.DOTALL
            )
            index_context = re.compile(
                r"<sitemapindex.*?</sitemapindex>", re.IGNORECASE | re.DOTALL
            )
            # Extract page URLs from <url> context
            for urlset_match in urlset_context.finditer(content):
                for match in loc_pattern.finditer(urlset_match.group(0)):
                    page_urls.append(match.group(1).strip())
            # Extract child sitemaps from <sitemap> context within sitemapindex
            for index_match in index_context.finditer(content):
                section = index_match.group(0)
                for sm in re.finditer(
                    r"<sitemap>\s*<loc>\s*(.*?)\s*</loc>\s*</sitemap>",
                    section,
                    re.IGNORECASE | re.DOTALL,
                ):
                    child_sitemaps.append(sm.group(1).strip())

        # Deduplicate page URLs while preserving order
        seen: set[str] = set()
        unique_pages = []
        for url in page_urls:
            if url not in seen:
                seen.add(url)
                unique_pages.append(url)
            if len(unique_pages) >= max_pages:
                break

        return unique_pages[:max_pages], child_sitemaps

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
