"""
Link extractor - dataclass definitions for crawler link facts.

.. deprecated::
    BS4 extraction has been removed. Use ``ParserOrchestrator`` + bridge
    (``parsed_document_to_page_facts``) instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup


@dataclass
class LinkFacts:
    links: list = field(default_factory=list)
    internal_count: int = 0
    external_count: int = 0
    deep_links: list = field(default_factory=list)
    total_link_count: int = 0
    fragment_count: int = 0
    mailto_count: int = 0
    tel_count: int = 0
    javascript_count: int = 0
    non_http_count: int = 0


def extract_links_from_html(html: str, base_url: str) -> list[dict]:
    """
    Extract links from HTML content using BeautifulSoup.
    
    This is a lightweight extraction used for rendered HTML comparison.
    Returns list of link dicts compatible with LinkAnalysisService.
    """
    soup = BeautifulSoup(html, "html.parser")
    results = []

    for tag in soup.find_all("a"):
        href = str(tag.get("href", "")).strip()
        if not href:
            continue

        rel = tag.get("rel", [])
        if isinstance(rel, str):
            rel = rel.split()
        rel = [str(value).strip().lower() for value in rel]

        # Capture raw attributes
        raw_attributes = {}
        for key, value in tag.attrs.items():
            if isinstance(value, list):
                raw_attributes[key] = " ".join(str(item) for item in value)
            else:
                raw_attributes[key] = str(value)

        results.append(
            {
                "url": urljoin(base_url, href),
                "anchor_text": tag.get_text(" ", strip=True),
                "rel": " ".join(rel) if rel else "",
                "link_type": "anchor",
                "is_internal": False,  # Will be computed later
                "is_external": False,  # Will be computed later
                "nofollow": "nofollow" in rel,
                "ugc": "ugc" in rel,
                "sponsored": "sponsored" in rel,
                "target": str(tag.get("target", "")).strip(),
                "title": str(tag.get("title", "")).strip(),
                "download": str(tag.get("download", "")).strip(),
                "raw_href": str(tag.get("href", "")),
                "raw_attributes": raw_attributes,
                "source": "rendered",
            }
        )

    return results
