"""
URL utility functions for normalization and validation.
"""
from urllib.parse import urlparse, urlunparse
from typing import Optional

# Public Suffix List — common multi-level TLDs that require special handling.
# Any host ending with one of these suffixes needs an extra label extracted
# to form the registered domain (eTLD+1).
_MULTI_LEVEL_SUFFIXES = (
    ".co.uk", ".org.uk", ".ac.uk", ".gov.uk", ".nhs.uk",
    ".co.in", ".org.in", ".ac.in", ".gov.in", ".nic.in",
    ".com.au", ".net.au", ".org.au", ".gov.au",
    ".co.jp", ".or.jp", ".ne.jp", ".go.jp",
    ".com.br", ".net.br", ".org.br", ".gov.br",
    ".co.nz", ".org.nz", ".net.nz",
    ".com.cn", ".net.cn", ".org.cn", ".gov.cn",
    ".co.za", ".org.za", ".net.za",
)


def _registered_domain(host: str) -> str:
    """
    Extract the registered domain (eTLD+1) from a hostname.

    Handles multi-level public suffixes (e.g. ``.co.uk``, ``.com.au``) so
    that subdomains of the same site compare equal:

    >>> _registered_domain("en.wikipedia.org")
    'wikipedia.org'
    >>> _registered_domain("www.wikipedia.org")
    'wikipedia.org'
    >>> _registered_domain("github.com")
    'github.com'
    >>> _registered_domain("docs.github.com")
    'github.com'
    >>> _registered_domain("shop.example.co.uk")
    'example.co.uk'

    Args:
        host: A bare hostname (no scheme, no path).

    Returns:
        The registered domain (registrable base domain, or eTLD+1).
    """
    host = host.strip().lower().rstrip(".")
    if not host:
        return ""

    # Strip port if present (IPv6 literals handled too).
    if host.startswith("["):
        # IPv6 literal — return as-is (no subdomains to speak of).
        return host
    if ":" in host:
        host = host.split(":", 1)[0]

    # Strip a single leading "www." prefix (proper prefix removal, not lstrip).
    if host.startswith("www."):
        host = host[4:]

    parts = host.split(".")
    if len(parts) < 2:
        return host

    # Check for multi-level suffixes first (e.g. ".co.uk" -> take last 3 labels).
    for suffix in _MULTI_LEVEL_SUFFIXES:
        if host.endswith(suffix):
            # Registered domain = suffix + one label (e.g. example.co.uk).
            # suffix_labels already = suffix levels + 1 (the registrable part).
            suffix_labels = suffix.count(".") + 1
            if len(parts) > suffix_labels:
                # Host has subdomains beyond the registered domain.
                return ".".join(parts[-suffix_labels:])
            return host  # Host IS the registered domain (e.g. example.co.uk)

    # Standard case: last two labels (e.g. "example.com").
    return ".".join(parts[-2:]) if len(parts) >= 2 else host

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

    Compares registered domains (eTLD+1) so that the apex host, its ``www.``
    variant, and all subdomains are considered the same site.

    Examples:
        >>> is_same_site("example.com", "www.example.com")
        True
        >>> is_same_site("www.example.com", "example.com")
        True
        >>> is_same_site("example.com", "blog.example.com")
        True
        >>> is_same_site("en.wikipedia.org", "www.wikipedia.org")
        True
        >>> is_same_site("docs.github.com", "github.com")
        True
        >>> is_same_site("example.com", "example.org")
        False
        >>> is_same_site("example.co.uk", "shop.example.co.uk")
        True

    Args:
        host_a: First host or netloc.
        host_b: Second host or netloc.

    Returns:
        True if the hosts are the same site, False otherwise.
    """
    return _registered_domain(host_a) == _registered_domain(host_b) and bool(_registered_domain(host_a))


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
