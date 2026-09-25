"""
Sitemap check input validation.

Accepts any URL (bare domain, full page URL, with/without scheme) and reduces
it to the site's origin — because sitemaps are declared at the host level
rather than per page.

Shares the same normalization rules as ``robots_check/validation.py``:
strips scheme, path, query, fragment, port, and a single leading ``www.``
prefix, returning the lowercase registered domain.
"""
from app.shared.utils.url_utils import normalize_host


class SitemapCheckValidationError(ValueError):
    """Raised when a sitemap check input fails validation."""


def validate_url(url: str) -> str:
    """Validate and normalize any URL to a bare domain.

    Accepts forms like ``example.com``, ``www.example.com``,
    ``https://example.com/path``, ``Example.COM:8080``,
    ``http://shop.example.co.uk/some/page``.

    Returns the lowercase registered domain (``normalize_host`` strips
    ``www.`` and the port).

    Raises:
        SitemapCheckValidationError: if *url* is empty or invalid.
    """
    if not isinstance(url, str) or not url.strip():
        raise SitemapCheckValidationError("url must be a non-empty string")

    cleaned = url.strip().lower()

    if "://" in cleaned:
        cleaned = cleaned.split("://", 1)[1]
    cleaned = cleaned.split("/", 1)[0]

    host = normalize_host(cleaned)
    if not host:
        raise SitemapCheckValidationError(f"Invalid url: {url!r}")

    if "." not in host and host != "localhost":
        raise SitemapCheckValidationError(
            f"Invalid url: {url!r} — "
            "expected a fully-qualified domain name (e.g. example.com)"
        )

    _SCHEME_NAMES = frozenset(
        {"http", "https", "ftp", "ftps", "htts", "sftp", "ws", "wss"}
    )
    if host in _SCHEME_NAMES:
        raise SitemapCheckValidationError(
            f"Invalid url: {url!r} — "
            "looks like a URL scheme, not a domain name"
        )

    return host


def build_sitemap_url(domain: str, path: str, scheme: str = "https") -> str:
    """Build a sitemap URL for *domain* + *path* (e.g. '/sitemap.xml')."""
    return f"{scheme}://{domain}{path}"
