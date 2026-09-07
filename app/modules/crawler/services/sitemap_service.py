"""
SitemapService - Discovers and parses XML sitemaps, sitemap indexes, and gzipped sitemaps.
"""
import gzip
from typing import List, Set
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import httpx

from app.shared.utils.url_utils import normalize_url


class SitemapResult:
    def __init__(self, url: str, status_code: int = 0, is_index: bool = False):
        self.url = url
        self.status_code = status_code
        self.is_index = is_index
        self.urls: List[str] = []
        self.child_sitemaps: List[str] = []


class SitemapService:
    """Service to fetch and extract URLs from sitemaps with recursive index expansion."""

    def __init__(self, max_sitemap_urls: int = 50000):
        self.max_sitemap_urls = max_sitemap_urls
        self.visited_sitemaps: Set[str] = set()

    async def fetch_and_parse(self, sitemap_url: str, timeout: float = 15.0) -> SitemapResult:
        normalized = normalize_url(sitemap_url)
        if normalized in self.visited_sitemaps:
            return SitemapResult(sitemap_url, status_code=0)
        self.visited_sitemaps.add(normalized)

        result = SitemapResult(sitemap_url)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                resp = await client.get(sitemap_url)
                result.status_code = resp.status_code
                if resp.status_code != 200:
                    return result

                content_bytes = resp.content
                if sitemap_url.endswith(".gz") or content_bytes[:2] == b"\x1f\x8b":
                    try:
                        content_bytes = gzip.decompress(content_bytes)
                    except Exception:
                        pass

                xml_text = content_bytes.decode("utf-8", errors="ignore")
                self._parse_xml(xml_text, result)

        except Exception:
            pass

        return result

    def _parse_xml(self, xml_text: str, result: SitemapResult) -> None:
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return

        tag_lower = root.tag.lower()
        if "sitemapindex" in tag_lower:
            result.is_index = True
            for elem in root.findall(".//{*}sitemap/{*}loc"):
                if elem.text and elem.text.strip():
                    result.child_sitemaps.append(elem.text.strip())
        elif "urlset" in tag_lower:
            for elem in root.findall(".//{*}url/{*}loc"):
                if elem.text and elem.text.strip():
                    result.urls.append(elem.text.strip())
                    if len(result.urls) >= self.max_sitemap_urls:
                        break
