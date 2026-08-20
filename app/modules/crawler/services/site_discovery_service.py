"""
Site discovery service - discovers robots.txt, sitemaps, and site-level data.

This service:
1. Fetches robots.txt
2. Fetches sitemap.xml and sitemap index files
3. Recursively expands sitemap-index child sitemaps
4. Extracts page URLs from all discovered sitemaps
5. Returns raw evidence

It does NOT:
- Write to PostgreSQL
- Score robots/sitemap compliance
"""
import gzip
from dataclasses import dataclass, field
from typing import List, Optional, Set
from urllib.parse import urljoin, urlparse

import xml.etree.ElementTree as ET

from app.core.logger import logger
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
    """Raw evidence from a single sitemap file."""
    url: str = ""
    exists: bool = False
    status_code: Optional[int] = None
    content_type: Optional[str] = None
    content_length: int = 0
    urls: list = field(default_factory=list)
    child_sitemaps: list = field(default_factory=list)
    is_index: bool = False
    error: Optional[str] = None


@dataclass
class SiteDiscoveryResult:
    """Combined site discovery result."""
    robots: RobotsTxtEvidence
    sitemaps: list = field(default_factory=list)
    discovered_urls: list = field(default_factory=list)


class SiteDiscoveryService:
    """Service for site-level discovery."""

    # Conservative safeguards for recursive sitemap-index expansion.
    # These are safe defaults; every value can be overridden per-instance.
    MAX_SITEMAP_INDEX_DEPTH: int = 3
    MAX_CHILD_SITEMAPS: int = 40
    MAX_URLS_PER_SITEMAP: int = 500
    MAX_TOTAL_PAGE_URLS: int = 500

    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        max_child_sitemaps: Optional[int] = None,
        max_urls_per_sitemap: Optional[int] = None,
        max_total_page_urls: Optional[int] = None,
        max_sitemap_index_depth: Optional[int] = None,
    ):
        self.base_url = base_url
        self.timeout = timeout
        parsed = urlparse(base_url)
        self.scheme = parsed.scheme
        self.domain = get_domain(base_url)

        self._max_sitemap_files = (
            max_child_sitemaps if max_child_sitemaps is not None else self.MAX_CHILD_SITEMAPS
        )
        self._max_urls_per_sitemap = (
            max_urls_per_sitemap if max_urls_per_sitemap is not None else self.MAX_URLS_PER_SITEMAP
        )
        self._max_total_page_urls = (
            max_total_page_urls if max_total_page_urls is not None else self.MAX_TOTAL_PAGE_URLS
        )
        self._max_sitemap_index_depth = (
            max_sitemap_index_depth if max_sitemap_index_depth is not None else self.MAX_SITEMAP_INDEX_DEPTH
        )

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
            discovered_urls.extend(sitemap.urls[: self._max_urls_per_sitemap])

        discovered_urls = discovered_urls[: self._max_total_page_urls]

        logger.info(
            "Site discovery complete for %s: robots=%s, sitemaps=%d, page_urls=%d",
            self.base_url,
            robots.exists,
            len(sitemaps),
            len(discovered_urls),
        )

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
            async with HTTPClient(timeout=self.timeout) as client:
                response = await client.get(robots_url)
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
                    logger.debug(
                        "Fetched robots.txt for %s: exists=%s, sitemaps=%d",
                        self.domain,
                        evidence.exists,
                        len(evidence.sitemap_references),
                    )
        except Exception:
            logger.debug("Failed to fetch robots.txt for %s", self.domain)

        return evidence

    async def _discover_sitemaps(self, robots: RobotsTxtEvidence) -> List[SitemapEvidence]:
        """Discover sitemaps from robots.txt references and common locations,
        recursively expanding any sitemap-index files."""
        sitemap_candidates = list(robots.sitemap_references)
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
            url = f"{self.scheme}://{self.domain}{path}"
            if url not in sitemap_candidates:
                sitemap_candidates.append(url)

        sitemaps: List[SitemapEvidence] = []
        seen: Set[str] = set()
        for sitemap_url in sitemap_candidates:
            if sitemap_url in seen:
                continue
            seen.add(sitemap_url)

            evidence = await self._fetch_sitemap(sitemap_url)
            if evidence.exists:
                sitemaps.append(evidence)
                if evidence.is_index:
                    await self._expand_sitemap_index(
                        evidence, seen, depth=1, sitemaps=sitemaps
                    )

        return sitemaps

    async def _expand_sitemap_index(
        self,
        index_evidence: SitemapEvidence,
        seen: Set[str],
        depth: int,
        sitemaps: List[SitemapEvidence],
    ) -> None:
        """Recursively fetch child sitemaps referenced by a sitemap-index file.

        Safeguards:
        - ``seen`` set prevents cycles and duplicate sitemap fetches.
        - ``depth`` is capped at ``MAX_SITEMAP_INDEX_DEPTH``.
        - ``sitemaps`` list is capped at ``MAX_CHILD_SITEMAPS`` entries.
        - Individual child-sitemap fetch failures are logged and skipped;
          they never abort the overall discovery.
        """
        for child_url in index_evidence.child_sitemaps:
            if child_url in seen:
                continue
            if depth > self._max_sitemap_index_depth:
                logger.debug(
                    "Sitemap index depth limit reached, skipping %s", child_url
                )
                continue
            if len(sitemaps) >= self._max_sitemap_files:
                logger.debug(
                    "Sitemap child limit (%d) reached, skipping %s",
                    self._max_sitemap_files,
                    child_url,
                )
                break

            seen.add(child_url)
            child_evidence = await self._fetch_sitemap(child_url)
            if child_evidence.exists:
                sitemaps.append(child_evidence)
                if child_evidence.is_index:
                    await self._expand_sitemap_index(
                        child_evidence, seen, depth=depth + 1, sitemaps=sitemaps
                    )
            if child_evidence.error:
                logger.debug(
                    "Sitemap child fetch failed for %s: %s",
                    child_url,
                    child_evidence.error,
                )

    async def _fetch_sitemap(self, sitemap_url: str) -> SitemapEvidence:
        """Fetch a sitemap and extract URLs and/or child sitemap references."""
        evidence = SitemapEvidence(url=sitemap_url)

        try:
            async with HTTPClient(timeout=self.timeout) as client:
                response = await client.get(sitemap_url)
                evidence.status_code = response.status_code
                evidence.content_type = response.headers.get("content-type", "")
                evidence.content_length = len(response.content)

                if response.status_code == 200 and response.content:
                    evidence.exists = True
                    content = response.content
                    # Handle gzip-compressed sitemaps
                    if "gzip" in evidence.content_type or sitemap_url.endswith(".gz"):
                        try:
                            content = gzip.decompress(content)
                        except Exception:
                            pass
                    text = content.decode("utf-8", errors="ignore")
                    self._parse_sitemap_xml(text, evidence, sitemap_url)
                    logger.debug(
                        "Fetched sitemap %s: status=%d, urls=%d, child_sitemaps=%d, is_index=%s",
                        sitemap_url,
                        evidence.status_code,
                        len(evidence.urls),
                        len(evidence.child_sitemaps),
                        evidence.is_index,
                    )
        except Exception as exc:
            evidence.error = str(exc)
            logger.debug(
                "Sitemap fetch failed for %s: %s", sitemap_url, exc
            )

        return evidence

    @staticmethod
    def _parse_sitemap_xml(
        xml_text: str,
        evidence: SitemapEvidence,
        sitemap_url: str,
    ) -> None:
        """Parse sitemap XML, populating ``urls`` (URL set) and
        ``child_sitemaps`` (index) using namespace-agnostic wildcards."""
        try:
            root = ET.fromstring(xml_text)

            for loc in root.findall(".//{*}url/{*}loc"):
                if loc.text and loc.text.strip():
                    resolved = urljoin(sitemap_url, loc.text.strip())
                    evidence.urls.append(resolved)

            for loc in root.findall(".//{*}sitemap/{*}loc"):
                if loc.text and loc.text.strip():
                    resolved = urljoin(sitemap_url, loc.text.strip())
                    evidence.child_sitemaps.append(resolved)

            evidence.is_index = len(evidence.child_sitemaps) > 0
        except ET.ParseError as exc:
            evidence.error = str(exc)
