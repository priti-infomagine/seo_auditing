"""
Asset extractor - extracts assets (images, CSS, JS, fonts, etc.) from HTML.
Returns structured asset data only, no persistence logic.
"""
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup


class ExtractedAsset:
    """Structured asset data."""
    def __init__(
        self,
        url: str,
        asset_type: str,
        mime_type: Optional[str] = None,
    ):
        self.url = url
        self.asset_type = asset_type
        self.mime_type = mime_type


def extract_assets(html: str, base_url: str) -> List[ExtractedAsset]:
    """
    Extract all assets from HTML content.
    
    Args:
        html: Raw HTML string
        base_url: Base URL for resolving relative links
        
    Returns:
        List of ExtractedAsset objects
    """
    soup = BeautifulSoup(html, "html.parser")
    assets = []
    
    # Images
    for tag in soup.find_all("img", src=True):
        src = str(tag.get("src", "")).strip()
        if src:
            assets.append(ExtractedAsset(
                url=urljoin(base_url, src),
                asset_type="image",
            ))
    
    # CSS
    for tag in soup.find_all("link", rel="stylesheet", href=True):
        href = str(tag.get("href", "")).strip()
        if href:
            assets.append(ExtractedAsset(
                url=urljoin(base_url, href),
                asset_type="css",
            ))
    
    # JavaScript
    for tag in soup.find_all("script", src=True):
        src = str(tag.get("src", "")).strip()
        if src:
            assets.append(ExtractedAsset(
                url=urljoin(base_url, src),
                asset_type="javascript",
            ))
    
    # Favicon
    for tag in soup.find_all("link", rel=["icon", "shortcut icon"], href=True):
        href = str(tag.get("href", "")).strip()
        if href:
            assets.append(ExtractedAsset(
                url=urljoin(base_url, href),
                asset_type="favicon",
            ))
    
    return assets