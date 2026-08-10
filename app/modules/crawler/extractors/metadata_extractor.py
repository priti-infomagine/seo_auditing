"""
Metadata extractor - extracts page metadata and social tags.
"""
from dataclasses import dataclass, field
from typing import Any
from bs4 import BeautifulSoup


@dataclass
class MetadataFacts:
    title: str = ""
    title_length: int = 0
    meta_description: str = ""
    meta_description_length: int = 0
    canonical: str = ""
    robots_meta: str = ""
    googlebot: str = ""
    viewport: str = ""
    charset: str = ""
    favicon: str = ""
    open_graph: dict = field(default_factory=dict)
    twitter: dict = field(default_factory=dict)
    hreflang: list = field(default_factory=list)


def extract_metadata(soup: BeautifulSoup, base_url: str = "") -> MetadataFacts:
    """
    Extract metadata from parsed HTML document.

    Args:
        soup: BeautifulSoup object
        base_url: Base URL for resolving relative URLs

    Returns:
        MetadataFacts with all metadata extracted
    """
    title = ""
    title_tag = soup.find("title")
    if title_tag and title_tag.string:
        title = title_tag.string.strip()

    meta_description = ""
    meta_desc_tag = soup.find("meta", attrs={"name": "description"})
    if meta_desc_tag:
        meta_description = meta_desc_tag.get("content", "").strip()

    canonical = ""
    canonical_tag = soup.find("link", attrs={"rel": "canonical"})
    if canonical_tag:
        canonical = canonical_tag.get("href", "").strip()

    robots_meta = ""
    robots_tag = soup.find("meta", attrs={"name": "robots"})
    if robots_tag:
        robots_meta = robots_tag.get("content", "").strip()

    googlebot = ""
    googlebot_tag = soup.find("meta", attrs={"name": "googlebot"})
    if googlebot_tag:
        googlebot = googlebot_tag.get("content", "").strip()

    viewport = ""
    viewport_meta = soup.find("meta", attrs={"name": "viewport"})
    if viewport_meta:
        viewport = viewport_meta.get("content", "").strip()

    charset = ""
    charset_meta = soup.find("meta", attrs={"charset": True})
    if charset_meta:
        charset = charset_meta.get("charset", "").strip().lower()

    favicon = ""
    favicon_tag = soup.find("link", rel="icon")
    if not favicon_tag:
        favicon_tag = soup.find("link", rel="shortcut icon")
    if favicon_tag:
        favicon = favicon_tag.get("href", "").strip()

    open_graph = _extract_open_graph(soup)
    twitter = _extract_twitter(soup)
    hreflang = _extract_hreflang(soup, base_url)

    return MetadataFacts(
        title=title,
        title_length=len(title),
        meta_description=meta_description,
        meta_description_length=len(meta_description),
        canonical=canonical,
        robots_meta=robots_meta,
        googlebot=googlebot,
        viewport=viewport,
        charset=charset,
        favicon=favicon,
        open_graph=open_graph,
        twitter=twitter,
        hreflang=hreflang,
    )


def _extract_open_graph(soup: BeautifulSoup) -> dict:
    og_tags = {}
    for tag in soup.find_all("meta", attrs={"property": lambda x: x and x.startswith("og:")}):
        prop = tag.get("property", "")
        content = tag.get("content", "")
        if prop and content:
            og_tags[prop.replace("og:", "").lower()] = content
    return og_tags


def _extract_twitter(soup: BeautifulSoup) -> dict:
    twitter_tags = {}
    for tag in soup.find_all("meta", attrs={"name": lambda x: x and x.startswith("twitter:")}):
        name = tag.get("name", "")
        content = tag.get("content", "")
        if name and content:
            twitter_tags[name.replace("twitter:", "").lower()] = content
    return twitter_tags


def _extract_hreflang(soup: BeautifulSoup, base_url: str) -> list:
    from urllib.parse import urljoin
    links = []
    for tag in soup.find_all("link", rel="alternate", hreflang=True, href=True):
        href = tag.get("href", "").strip()
        if href:
            links.append({
                "url": urljoin(base_url, href),
                "hreflang": tag.get("hreflang", ""),
            })
    return links
