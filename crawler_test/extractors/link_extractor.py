"""
Link extractor - extracts links from HTML content.
Returns structured link data only, no persistence logic.
"""
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class ExtractedLink:
    """Structured link data."""
    def __init__(
        self,
        url: str,
        anchor_text: Optional[str] = None,
        rel: Optional[str] = None,
        link_type: str = "anchor",
    ):
        self.url = url
        self.anchor_text = anchor_text
        self.rel = rel
        self.link_type = link_type


def extract_links(html: str, base_url: str) -> List[ExtractedLink]:
    """
    Extract all links from HTML content.
    
    Args:
        html: Raw HTML string
        base_url: Base URL for resolving relative links
        
    Returns:
        List of ExtractedLink objects
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []
    
    # Extract <a> tags
    for tag in soup.find_all("a", href=True):
        href = str(tag.get("href", "")).strip()
        if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
            absolute_url = urljoin(base_url, href)
            anchor_text = tag.get_text(strip=True) or None
            rel = tag.get("rel")
            if isinstance(rel, list):
                rel = rel[0] if rel else None
            elif rel is not None:
                rel = str(rel)
            links.append(ExtractedLink(
                url=absolute_url,
                anchor_text=anchor_text,
                rel=rel,
                link_type="anchor",
            ))
    
    # Extract canonical links
    for tag in soup.find_all("link", rel="canonical", href=True):
        href = str(tag.get("href", "")).strip()
        if href:
            absolute_url = urljoin(base_url, href)
            links.append(ExtractedLink(
                url=absolute_url,
                link_type="canonical",
            ))
    
    # Extract hreflang links
    for tag in soup.find_all("link", rel="alternate", hreflang=True, href=True):
        href = str(tag.get("href", "")).strip()
        if href:
            absolute_url = urljoin(base_url, href)
            hreflang = tag.get("hreflang")
            rel = str(hreflang) if hreflang else None
            links.append(ExtractedLink(
                url=absolute_url,
                rel=rel,
                link_type="hreflang",
            ))
    
    return links