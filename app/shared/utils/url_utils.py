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


def normalize_host(host: str) -> str:
    """
    Normalize a host (or netloc) for same-site comparison.

    Normalization rules:
    - Lowercase
    - Strip trailing dot (FQDN root label)
    - Strip the port (if present)
    - Strip a single optional leading ``www.`` prefix

    After normalization ``example.com`` and ``www.example.com`` compare
    equal, while arbitrary subdomains (``blog.example.com``) remain distinct
    and are treated as external by default.

    Args:
        host: A bare hostname, a netloc (``host`` or ``host:port``),
              or an IPv6 literal (``[::1]``).

    Returns:
        The normalized hostname (lowercase, no port, no leading ``www.``).
    """
    if not host:
        return ""
    host = host.strip().lower().rstrip(".")

    if host.startswith("["):
        idx = host.find("]")
        if idx != -1:
            host = host[1:idx]
    else:
        if ":" in host:
            host = host.split(":", 1)[0]

    if host.startswith("www."):
        host = host[4:]
    return host


def is_same_site(host_a: str, host_b: str) -> bool:
    """
    Determine whether two hosts belong to the same site.

    Uses :func:`normalize_host` so that the apex host and its ``www.``
    variant are considered equivalent, but arbitrary subdomains are not.

    Examples:
        >>> is_same_site("example.com", "www.example.com")
        True
        >>> is_same_site("www.example.com", "example.com")
        True
        >>> is_same_site("example.com", "blog.example.com")
        False
        >>> is_same_site("example.com", "example.org")
        False

    Args:
        host_a: First host or netloc.
        host_b: Second host or netloc.

    Returns:
        True if the hosts are the same site, False otherwise.
    """
    return normalize_host(host_a) == normalize_host(host_b)


def is_internal_link(base_url: str, target_url: str) -> bool:
    """
    Check if target_url is internal to base_url.
    
    Uses same-site comparison so that apex and ``www.`` variants of the
    same site are treated as internal.
    
    Args:
        base_url: The base URL
        target_url: The target URL to check
        
    Returns:
        True if internal, False otherwise
    """
    base_domain = get_domain(base_url)
    target_domain = get_domain(target_url)
    if not base_domain or not target_domain:
        return False
    return is_same_site(base_domain, target_domain)
