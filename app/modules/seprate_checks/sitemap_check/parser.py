"""
Sitemap XML parser.

Parses sitemap XML (and sitemap-index XML) into a structured result with
namespace-agnostic XPath queries (the same technique used by
``SiteDiscoveryService._parse_sitemap_xml``).

This module also re-exports ``parse_robots_sitemaps`` — a thin wrapper over
the robots_check parser (``protego``) that extracts declared ``Sitemap:``
locations from robots.txt text.  Reusing protego avoids duplicating the
robots.txt spec-compliance work already done in ``robots_check.parser``.
"""
import gzip
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Optional

from app.core.logger import logger


@dataclass(slots=True)
class SitemapParseResult:
    """Parsed sitemap file — URLs, child sitemaps, entry count, type."""

    loc_urls: list[str] = field(default_factory=list)
    child_sitemaps: list[str] = field(default_factory=list)
    is_index: bool = False
    entry_count: int = 0
    error: Optional[str] = None


def parse_sitemap_xml(xml_text: str) -> SitemapParseResult:
    """Parse sitemap XML text into a :class:`SitemapParseResult`.

    Handles both ``<urlset>`` (regular sitemap) and ``<sitemapindex>``
    (sitemap index) documents.  Namespace-agnostic so it works with the
    default sitemap namespace, Google News, etc.

    Non-blocking: parse errors are captured in ``error`` and the result
    returns with zero counts rather than raising.
    """
    if not xml_text or not xml_text.strip():
        return SitemapParseResult(error="Empty sitemap content")

    result = SitemapParseResult()

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        result.error = f"XML parse error: {exc}"
        logger.debug("parse_sitemap_xml: %s", exc)
        return result

    for loc in root.findall(".//{*}url/{*}loc"):
        url = (loc.text or "").strip()
        if url:
            result.loc_urls.append(url)

    for loc in root.findall(".//{*}sitemap/{*}loc"):
        url = (loc.text or "").strip()
        if url:
            result.child_sitemaps.append(url)

    result.is_index = len(result.child_sitemaps) > 0
    result.entry_count = len(result.loc_urls) + len(result.child_sitemaps)

    return result


def decompress_sitemap_content(
    content: bytes, content_type: str = "", url: str = ""
) -> tuple[bytes, bool]:
    """Decompress gzip content if needed.

    Sitemaps are commonly served as ``.xml.gz`` or with
    ``Content-Type: application/gzip`` / ``application/x-gzip``.

    Args:
        content: Raw response bytes.
        content_type: The Content-Type header (may contain ``gzip``).
        url: The sitemap URL (checked for ``.gz`` suffix).

    Returns:
        Tuple of (decompressed_content, was_gzipped).
    """
    is_gzipped = (
        "gzip" in content_type.lower()
        or url.endswith(".gz")
    )

    if not is_gzipped:
        try:
            if len(content) >= 2 and content[0] == 0x1F and content[1] == 0x8B:
                is_gzipped = True
        except (IndexError, TypeError):
            pass

    if is_gzipped:
        try:
            return gzip.decompress(content), True
        except Exception as exc:
            logger.debug("decompress_sitemap_content: gzip decompress failed: %s", exc)
            return content, False

    return content, False


def parse_robots_sitemaps(robots_text: str) -> list[str]:
    """Extract ``Sitemap:`` locations from raw robots.txt text.

    Delegates to ``protego`` (via ``robots_check.parser``) for spec-compliant
    parsing.  If protego fails, falls back to a simple regex scan so we
    never lose manually-declared sitemaps due to a parser edge case.
    """
    if not robots_text or not robots_text.strip():
        return []

    sitemaps: list[str] = []

    try:
        from app.modules.seprate_checks.robots_check.parser import (
            parse_robots_txt,
        )

        parsed = parse_robots_txt(robots_text)
        sitemaps = list(parsed.sitemaps)
    except Exception as exc:
        logger.debug("parse_robots_sitemaps: protego parse failed: %s", exc)

    if not sitemaps:
        import re

        for line in robots_text.splitlines():
            match = re.match(
                r"^\s*sitemap\s*:\s*(.+?)\s*$",
                line,
                re.IGNORECASE,
            )
            if match:
                url = match.group(1).strip()
                if url.startswith("#"):
                    continue
                sitemaps.append(url)

    return sitemaps
