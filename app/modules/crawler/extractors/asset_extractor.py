"""
Asset extractor - extracts resources (images, CSS, JS, fonts, etc.) from HTML.
"""
from dataclasses import dataclass, field
from urllib.parse import urljoin
from bs4 import BeautifulSoup


@dataclass
class ResourceFacts:
    resources: list = field(default_factory=list)


def extract_resources(soup: BeautifulSoup, base_url: str) -> ResourceFacts:
    """
    Extract all resources from HTML content.

    Args:
        soup: BeautifulSoup object
        base_url: Base URL for resolving relative URLs

    Returns:
        ResourceFacts with all extracted resources
    """
    resources = []

    # Images
    for tag in soup.find_all("img", src=True):
        src = str(tag.get("src", "")).strip()
        if not src:
            continue

        alt = tag.get("alt", "")
        width = tag.get("width")
        height = tag.get("height")
        loading = tag.get("loading", "")
        srcset = tag.get("srcset", "")
        sizes = tag.get("sizes", "")

        resources.append({
            "type": "image",
            "url": urljoin(base_url, src),
            "alt": alt,
            "width": int(width) if width and width.isdigit() else None,
            "height": int(height) if height and height.isdigit() else None,
            "loading": loading if loading else None,
            "srcset": srcset if srcset else None,
            "sizes": sizes if sizes else None,
            "is_lazy": loading == "lazy",
        })

    # CSS
    for tag in soup.find_all("link", rel="stylesheet", href=True):
        href = tag.get("href", "").strip()
        if href:
            resources.append({
                "type": "css",
                "url": urljoin(base_url, href),
                "media": tag.get("media", ""),
            })

    # JavaScript
    for tag in soup.find_all("script", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "javascript",
                "url": urljoin(base_url, src),
                "async": tag.get("async") is not None,
                "defer": tag.get("defer") is not None,
            })

    # Favicon
    for tag in soup.find_all("link", rel=["icon", "shortcut icon"], href=True):
        href = tag.get("href", "").strip()
        if href:
            resources.append({
                "type": "favicon",
                "url": urljoin(base_url, href),
            })

    # Iframe
    for tag in soup.find_all("iframe", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "iframe",
                "url": urljoin(base_url, src),
            })

    # Video
    for tag in soup.find_all("video", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "video",
                "url": urljoin(base_url, src),
            })

    # Audio
    for tag in soup.find_all("audio", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "audio",
                "url": urljoin(base_url, src),
            })

    return ResourceFacts(resources=resources)
