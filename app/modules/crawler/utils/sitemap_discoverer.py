"""
SitemapDiscoverer - Parses XML sitemaps, sitemap indexes, and .gz compressed sitemaps.
"""
import gzip
import io
import xml.etree.ElementTree as ET
from typing import List, Optional

from app.shared.utils.http_client import HTTPClient


SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


class SitemapDiscoverer:
    """Fetches and parses sitemap files."""

    async def discover(self, sitemap_url: str, timeout: int = 30) -> List[str]:
        urls = []
        try:
            async with HTTPClient(sitemap_url, timeout=timeout) as response:
                if response.status_code != 200:
                    return urls
                content = response.content
                content_type = response.headers.get("content-type", "")
                if "gzip" in content_type or sitemap_url.endswith(".gz"):
                    content = gzip.decompress(content)
                text = content.decode("utf-8", errors="ignore")
                urls = self._parse_xml(text)
        except Exception:
            pass
        return urls

    def _parse_xml(self, xml_text: str) -> List[str]:
        urls = []
        try:
            root = ET.fromstring(xml_text)
            tag = f"{{{SITEMAP_NS}}}url"
            for url_elem in root.iter(tag):
                loc = url_elem.find(f"{{{SITEMAP_NS}}}loc")
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
        except ET.ParseError:
            pass
        return urls
