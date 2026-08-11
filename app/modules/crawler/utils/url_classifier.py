"""
URL classifier - determines the type and crawl eligibility of a URL.

Used by CrawlQueueService to filter non-HTML and non-crawlable URLs
before they enter the fetch queue.
"""
from urllib.parse import urlparse

from app.shared.utils.url_utils import normalize_url


class UrlClassification:
    HTML = "HTML"
    RESOURCE = "RESOURCE"
    API = "API"
    ROBOTS = "ROBOTS"
    SITEMAP = "SITEMAP"
    EXTERNAL = "EXTERNAL"
    INVALID = "INVALID"
    IGNORED = "IGNORED"
    FRAGMENT = "FRAGMENT"


# Paths that should never be crawled as HTML pages
_IGNORED_PATHS = {
    "/wp-admin", "/admin", "/login", "/logout",
    "/register", "/signup", "/account", "/profile",
    "/cart", "/checkout", "/payment",
}

# Path prefixes that should never be crawled as HTML pages
_IGNORED_PATH_PREFIXES = (
    "/wp-admin/", "/admin/", "/cart/", "/checkout/", "/payment/", "/account/", "/profile/",
)

# Tracking parameters to strip before dedup
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "ref", "source",
}

# File extensions that indicate non-HTML resources
_RESOURCE_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp",
    ".gif", ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".eot",
    ".mp4", ".mp3", ".avi", ".mov", ".zip", ".tar", ".gz",
}

# API / non-HTML path patterns
_API_PATH_PREFIXES = (
    "/wp-json/", "/api/", "/graphql",
)

# API / non-HTML file extensions
_API_EXTENSIONS = {".json", ".xml"}

# Faceted URL indicators
_FACETED_PARAM_PREFIXES = (
    "sort", "filter", "page", "q", "search",
)


def _get_domain(url: str) -> str:
    """Extract netloc from a URL, handling bare domains."""
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.lower()
    # Handle bare domains like "example.com" (no scheme)
    path = parsed.path or ""
    if "/" not in path and "." in path:
        return path.lower()
    return ""


def classify_url(url: str, base_domain: str = "") -> tuple[str, str]:
    """
    Classify a URL and return (classification, reason).

    Args:
        url: URL to classify
        base_domain: Base domain for internal/external determination

    Returns:
        (classification, reason) where classification is one of the
        UrlClassification constants.
    """
    if not url or not url.strip():
        return UrlClassification.INVALID, "empty_url"

    url = url.strip()

    # Fragment-only URLs
    if url.startswith("#"):
        return UrlClassification.FRAGMENT, "fragment_only"

    # Invalid schemes
    try:
        parsed = urlparse(url)
    except Exception:
        return UrlClassification.INVALID, "malformed_url"

    if parsed.scheme and parsed.scheme.lower() not in ("http", "https", ""):
        return UrlClassification.INVALID, f"unsupported_scheme:{parsed.scheme}"

    # Special protocols
    if parsed.scheme.lower() in ("mailto", "tel", "javascript", "data", "blob", "file"):
        return UrlClassification.INVALID, f"unsupported_scheme:{parsed.scheme}"

    # External domain check - compare netlocs directly
    if base_domain:
        target_domain = _get_domain(url)
        if target_domain and target_domain != base_domain.lower():
            return UrlClassification.EXTERNAL, "external_domain"

    path = parsed.path.lower()

    # Exact ignored paths
    if path in _IGNORED_PATHS:
        return UrlClassification.IGNORED, f"ignored_path:{path}"

    # Ignored path prefixes
    for prefix in _IGNORED_PATH_PREFIXES:
        if path.startswith(prefix):
            return UrlClassification.IGNORED, f"ignored_path_prefix:{prefix}"

    # Special files (must check before generic extension checks)
    if path == "/robots.txt" or path.endswith("/robots.txt"):
        return UrlClassification.ROBOTS, "robots_txt"

    if path in ("/sitemap.xml", "/sitemap_index.xml") or path.endswith("/sitemap.xml") or path.endswith("/sitemap_index.xml"):
        return UrlClassification.SITEMAP, "sitemap"

    # Resource extensions
    for ext in _RESOURCE_EXTENSIONS:
        if path.endswith(ext):
            return UrlClassification.RESOURCE, f"resource_extension:{ext}"

    # API paths and extensions
    for prefix in _API_PATH_PREFIXES:
        if path.startswith(prefix):
            return UrlClassification.API, f"api_path:{prefix}"

    for ext in _API_EXTENSIONS:
        if path.endswith(ext):
            return UrlClassification.API, f"api_extension:{ext}"

    # Faceted URLs (heuristic: multiple filter/sort params)
    if parsed.query:
        query_params = _extract_query_param_names(parsed.query)
        faceted_count = sum(1 for p in query_params if p.lower() in _FACETED_PARAM_PREFIXES)
        if faceted_count >= 2:
            return UrlClassification.IGNORED, "faceted_url"

    return UrlClassification.HTML, "eligible"


def _extract_query_param_names(query: str) -> list[str]:
    """Extract parameter names from a query string."""
    if not query:
        return []
    return [part.split("=")[0] for part in query.split("&") if "=" in part]


def strip_tracking_params(url: str) -> str:
    """
    Remove tracking parameters from a URL for cleaner deduplication.

    Args:
        url: URL string

    Returns:
        URL with tracking parameters removed
    """
    parsed = urlparse(url)
    if not parsed.query:
        return url

    params = [
        part for part in parsed.query.split("&")
        if part.split("=")[0].lower() not in _TRACKING_PARAMS
    ]
    new_query = "&".join(params)

    return parsed._replace(query=new_query).geturl()
