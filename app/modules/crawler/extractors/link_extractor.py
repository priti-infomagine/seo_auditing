"""
Link extractor - extracts links from HTML content.
"""
from dataclasses import dataclass, field
from urllib.parse import urljoin
from bs4 import BeautifulSoup


@dataclass
class LinkFacts:
    links: list = field(default_factory=list)
    internal_count: int = 0
    external_count: int = 0


def extract_links(soup: BeautifulSoup, base_url: str) -> LinkFacts:
    """
    Extract all links from HTML content.

    Args:
        soup: BeautifulSoup object
        base_url: Base URL for resolving relative links

    Returns:
        LinkFacts with all extracted links
    """
    from app.shared.utils.url_utils import is_internal_link

    links = []
    internal_count = 0
    external_count = 0

    # Extract <a> tags
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href", "")).strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
            continue

        absolute_url = urljoin(base_url, href)
        anchor_text = tag.get_text(strip=True) or ""
        rel = tag.get("rel")
        if isinstance(rel, list):
            rel = " ".join(rel)
        elif rel is None:
            rel = ""

        rel_lower = rel.lower()
        is_internal = is_internal_link(base_url, absolute_url)

        link_type = "anchor"
        if tag.find_parent("nav"):
            link_type = "navigation"
        elif tag.find_parent("footer"):
            link_type = "footer"

        links.append({
            "url": absolute_url,
            "anchor_text": anchor_text,
            "rel": rel,
            "link_type": link_type,
            "is_internal": is_internal,
            "is_external": not is_internal,
            "nofollow": "nofollow" in rel_lower,
            "ugc": "ugc" in rel_lower,
            "sponsored": "sponsored" in rel_lower,
        })

        if is_internal:
            internal_count += 1
        else:
            external_count += 1

    # Extract canonical links
    for tag in soup.find_all("link", rel="canonical", href=True):
        href = tag.get("href", "").strip()
        if href:
            absolute_url = urljoin(base_url, href)
            links.append({
                "url": absolute_url,
                "anchor_text": "",
                "rel": "canonical",
                "link_type": "canonical",
                "is_internal": True,
                "is_external": False,
                "nofollow": False,
                "ugc": False,
                "sponsored": False,
            })
            internal_count += 1

    # Extract hreflang links
    for tag in soup.find_all("link", rel="alternate", hreflang=True, href=True):
        href = tag.get("href", "").strip()
        if href:
            absolute_url = urljoin(base_url, href)
            links.append({
                "url": absolute_url,
                "anchor_text": "",
                "rel": tag.get("hreflang", ""),
                "link_type": "hreflang",
                "is_internal": True,
                "is_external": False,
                "nofollow": False,
                "ugc": False,
                "sponsored": False,
            })
            internal_count += 1

    return LinkFacts(
        links=links,
        internal_count=internal_count,
        external_count=external_count,
    )
