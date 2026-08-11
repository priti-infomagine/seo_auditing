"""
Asset extractor - extracts resources (images, CSS, JS, fonts, etc.) from HTML.
"""
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup


TYPE_TO_MIME = {
    "image": "image/*",
    "css": "text/css",
    "javascript": "application/javascript",
    "favicon": "image/x-icon",
    "iframe": "text/html",
    "video": "video/*",
    "audio": "audio/*",
}


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
            "mime_type": TYPE_TO_MIME.get("image", "image/*"),
        })

    for tag in soup.find_all("link", rel="stylesheet", href=True):
        href = tag.get("href", "").strip()
        if href:
            resources.append({
                "type": "css",
                "url": urljoin(base_url, href),
                "media": tag.get("media", ""),
                "mime_type": TYPE_TO_MIME.get("css", "text/css"),
            })

    for tag in soup.find_all("script", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "javascript",
                "url": urljoin(base_url, src),
                "async": tag.get("async") is not None,
                "defer": tag.get("defer") is not None,
                "mime_type": TYPE_TO_MIME.get("javascript", "application/javascript"),
            })

    for tag in soup.find_all("link", rel=["icon", "shortcut icon"], href=True):
        href = tag.get("href", "").strip()
        if href:
            resources.append({
                "type": "favicon",
                "url": urljoin(base_url, href),
                "mime_type": TYPE_TO_MIME.get("favicon", "image/x-icon"),
            })

    for tag in soup.find_all("iframe", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "iframe",
                "url": urljoin(base_url, src),
                "mime_type": TYPE_TO_MIME.get("iframe", "text/html"),
            })

    for tag in soup.find_all("video", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "video",
                "url": urljoin(base_url, src),
                "mime_type": TYPE_TO_MIME.get("video", "video/*"),
            })

    for tag in soup.find_all("audio", src=True):
        src = tag.get("src", "").strip()
        if src:
            resources.append({
                "type": "audio",
                "url": urljoin(base_url, src),
                "mime_type": TYPE_TO_MIME.get("audio", "audio/*"),
            })

    return ResourceFacts(resources=resources)
