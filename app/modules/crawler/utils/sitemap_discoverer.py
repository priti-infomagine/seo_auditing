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
    """Fetches and parses sitemap files, including sitemap indexes."""

    async def discover(self, sitemap_url: str, timeout: int = 30) -> List[str]:
        urls = []
        try:
            async with HTTPClient(timeout=timeout) as client:
                response = await client.get(sitemap_url)
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
        """Parse a sitemap XML file.

        Supports both URL-set files (``<url><loc>``) and sitemap-index
        files (``<sitemap><loc>``).  For index files the child sitemap
        URLs are returned so the caller can recursively expand them.
        """
        urls = []
        try:
            root = ET.fromstring(xml_text)

            ns_tag = f"{{{SITEMAP_NS}}}"

            # Collect <url><loc> entries (URL set)
            for url_elem in root.iter(f"{ns_tag}url"):
                loc = url_elem.find(f"{ns_tag}loc")
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())

            # Collect <sitemap><loc> entries (index file)
            for sm_elem in root.iter(f"{ns_tag}sitemap"):
                loc = sm_elem.find(f"{ns_tag}loc")
                if loc is not None and loc.text:
                    urls.append(loc.text.strip())
        except ET.ParseError:
            pass
        return urls

    def parse_index(self, xml_text: str) -> List[str]:
        """Extract child sitemap URLs from a sitemap-index XML file."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        if not self._is_index(root):
            return []
        return [
            loc.text.strip()
            for loc in root.iter(f"{{{SITEMAP_NS}}}loc")
            if loc.text and loc.text.strip()
        ]

    @staticmethod
    def _is_index(root: ET.Element) -> bool:
        """Return True if the parsed XML root represents a sitemap-index file."""
        return root.tag.endswith("sitemapindex")
