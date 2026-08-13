"""
URL utility functions for normalization and validation.
"""
from urllib.parse import urlparse, urlunparse
from typing import Optional 

def normalize_url(url: str) -> str:
    """
    Normalize a URL for crawler deduplication.

    Normalization:
    - Lowercases scheme and hostname.
    - Removes URL fragments.
    - Removes default HTTP/HTTPS ports.
    - Ensures the URL has a path.
    - Preserves the query string.
    - Removes surrounding whitespace.

    Args:
        url: URL to normalize.

    Returns:
        Normalized URL string.

    Raises:
        ValueError: If the URL has no valid scheme or hostname.
    """
    url = url.strip()

    if not url:
        raise ValueError("URL cannot be empty")

    parsed = urlparse(url)

    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme!r}")

    if not parsed.hostname:
        raise ValueError(f"Invalid URL: {url!r}")

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower()

    # Preserve username/password if present.
    netloc = hostname

    if parsed.username is not None:
        netloc = f"{parsed.username}"
        if parsed.password is not None:
            netloc += f":{parsed.password}"
        netloc += f"@{hostname}"

    # Remove default ports.
    port = parsed.port

    if port is not None:
        is_default_port = (
            (scheme == "http" and port == 80)
            or (scheme == "https" and port == 443)
        )

        if not is_default_port:
            netloc += f":{port}"

    # Empty path becomes "/".
    path = parsed.path or "/"

    # Fragment is deliberately removed.
    return urlunparse(
        (
            scheme,
            netloc,
            path,
            parsed.params,
            parsed.query,
            "",
        )
    )

def is_valid_url(url: str) -> bool:
    """
    Check if a URL is valid.
    
    Args:
        url: The URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except Exception:
        return False


def get_domain(url: str) -> Optional[str]:
    """
    Extract domain from URL.
    
    Args:
        url: The URL to extract domain from
        
    Returns:
        Domain string or None if invalid
    """
    try:
        parsed = urlparse(url)
        return parsed.netloc
    except Exception:
        return None


def is_internal_link(base_url: str, target_url: str) -> bool:
    """
    Check if target_url is internal to base_url.
    
    Args:
        base_url: The base URL
        target_url: The target URL to check
        
    Returns:
        True if internal, False otherwise
    """
    base_domain = get_domain(base_url)
    target_domain = get_domain(target_url)
    return base_domain == target_domain