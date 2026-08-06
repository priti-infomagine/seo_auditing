"""
MIME type detection utility.
"""
from typing import Optional


def detect_mime_type(content_type: Optional[str], url: str) -> Optional[str]:
    """
    Detect MIME type from content-type header or URL extension.
    
    Args:
        content_type: Content-Type header value
        url: URL to check for extension
        
    Returns:
        MIME type string or None
    """
    if content_type:
        return content_type.split(";")[0].strip().lower()
    
    # Fallback to URL extension
    ext_to_mime = {
        ".html": "text/html",
        ".htm": "text/html",
        ".css": "text/css",
        ".js": "application/javascript",
        ".json": "application/json",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
        ".ico": "image/x-icon",
        ".pdf": "application/pdf",
        ".woff": "font/woff",
        ".woff2": "font/woff2",
        ".ttf": "font/ttf",
        ".mp4": "video/mp4",
    }
    
    from urllib.parse import urlparse
    path = urlparse(url).path.lower()
    for ext, mime in ext_to_mime.items():
        if path.endswith(ext):
            return mime
    
    return None