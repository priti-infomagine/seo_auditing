"""
URLDiscoverer - Discovers URLs from HTML, sitemaps, and robots.txt with provenance tracking.
"""
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from app.modules.crawler.types import DiscoveredURL
from app.modules.crawler.utils.url_classifier import classify_url
from app.shared.utils.url_utils import normalize_url


class URLDiscoverer:
    """Discovers URLs from various sources with link provenance tracking."""

    def discover_from_html(
        self,
        html: str,
        source_url: str,
        base_domain: str,
        depth: int = 0,
        parent_page_id: Optional[str] = None,
    ) -> List[DiscoveredURL]:
        from bs4 import BeautifulSoup

        discovered = []
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return discovered

        # Extract <a> tags
        for tag in soup.find_all("a", href=True):
            href = tag.get("href", "").strip()
            if not href:
                continue
            absolute = urljoin(source_url, href)
            classification, _ = classify_url(absolute, base_domain)
            if classification != "HTML":
                continue
            try:
                discovered.append(
                    DiscoveredURL(
                        url=absolute,
                        normalized_url=normalize_url(absolute),
                        source_url=source_url,
                        source_type="html_link",
                        depth=depth + 1,
                        parent_page_id=parent_page_id,
                    )
                )
            except Exception:
                continue

        # Extract canonical
        for tag in soup.find_all("link", rel="canonical", href=True):
            href = tag.get("href", "").strip()
            if not href:
                continue
            absolute = urljoin(source_url, href)
            try:
                discovered.append(
                    DiscoveredURL(
                        url=absolute,
                        normalized_url=normalize_url(absolute),
                        source_url=source_url,
                        source_type="canonical",
                        depth=depth,
                        parent_page_id=parent_page_id,
                    )
                )
            except Exception:
                continue

        # Extract hreflang
        for tag in soup.find_all("link", rel="alternate", hreflang=True, href=True):
            href = tag.get("href", "").strip()
            if not href:
                continue
            absolute = urljoin(source_url, href)
            try:
                discovered.append(
                    DiscoveredURL(
                        url=absolute,
                        normalized_url=normalize_url(absolute),
                        source_url=source_url,
                        source_type="hreflang",
                        depth=depth,
                        parent_page_id=parent_page_id,
                    )
                )
            except Exception:
                continue

        return discovered

    def discover_from_sitemap(self, sitemap_url: str, base_domain: str) -> List[DiscoveredURL]:
        return []

    def discover_from_robots(self, robots_txt: str, base_domain: str) -> List[DiscoveredURL]:
        return []
