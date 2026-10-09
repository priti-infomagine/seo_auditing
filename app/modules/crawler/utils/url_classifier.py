"""
URL classifier - determines the type and crawl eligibility of a URL.

Used by CrawlQueueService to filter non-HTML and non-crawlable URLs
before they enter the fetch queue.
"""
from urllib.parse import urlparse

from app.shared.utils.url_utils import is_same_site, normalize_url


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
    "/wp-admin", "/admin", "/administrator", "/login", "/signin", "/logout",
    "/register", "/signup", "/account", "/my-account", "/dashboard", "/profile",
    "/orders", "/cart", "/basket", "/checkout", "/wishlist", "/payment",
    "/billing", "/forgot-password", "/reset-password", "/delete", "/remove",
    "/add-to-cart", "/add-to-wishlist", "/vote", "/confirm", "/verify",
    "/activate", "/cpanel", "/phpmyadmin", "/graphql", "/xmlrpc.php",
    "/.env",
}

# Path prefixes that should never be crawled as HTML pages
_IGNORED_PATH_PREFIXES = (
    "/wp-admin/", "/admin/", "/cart/", "/checkout/", "/payment/",
    "/account/", "/profile/", "/auth/", "/orders/", "/billing/",
    "/dashboard/", "/portal/", "/cpanel/", "/cdn-cgi/", "/.well-known/",
    "/.git/", "/cgi-bin/",
)

# Tracking parameters to strip before dedup
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "msclkid", "ref", "source", "sessionid", "sid",
    "token", "replytocom",
}

# File extensions that indicate non-HTML resources
_RESOURCE_EXTENSIONS = {
    ".css", ".js", ".png", ".jpg", ".jpeg", ".svg", ".webp",
    ".gif", ".ico", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".ppt", ".pptx", ".csv", ".txt", ".woff", ".woff2", ".ttf",
    ".eot", ".mp4", ".mp3", ".avi", ".mov", ".wav", ".zip",
    ".tar", ".gz", ".rar", ".webmanifest",
}

# API / non-HTML path patterns
_API_PATH_PREFIXES = (
    "/wp-json/", "/api/", "/graphql",
)

# API / non-HTML file extensions
_API_EXTENSIONS = {".json", ".xml"}

# Faceted URL indicators
_FACETED_PARAM_PREFIXES = (
    "sort", "filter", "page", "q", "search", "p", "price_min", "price_max", "color", "size", "view", "display", "order",
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


import re

# Repeating directory loop detector: e.g. /a/b/a/b/a/b
_REPEATING_PATH_PATTERN = re.compile(r'(/[^/]+)(/\1){2,}', re.IGNORECASE)
# Calendar / infinite archive loop detector: e.g. /events/2031/05
_CALENDAR_PATTERN = re.compile(r'/(?:events|calendar|archive)/\d{4}/\d{2}', re.IGNORECASE)


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
    if parsed.scheme.lower() in ("mailto", "tel", "javascript", "data", "blob", "file", "sms", "whatsapp"):
        return UrlClassification.INVALID, f"unsupported_scheme:{parsed.scheme}"

    # External domain check - compare hosts via same-site normalization so
    # that apex <-> www variants are treated as one site while arbitrary
    # subdomains (blog.example.com, api.example.com) remain external.
    if base_domain:
        target_domain = _get_domain(url)
        if target_domain and not is_same_site(target_domain, base_domain):
            return UrlClassification.EXTERNAL, "external_domain"

    path = parsed.path.lower()

    # Crawl traps: Repeating directory loops (e.g. /a/b/a/b/a/b)
    if _REPEATING_PATH_PATTERN.search(path):
        return UrlClassification.IGNORED, "repeating_path_loop"

    # Crawl traps: Infinite calendar/archive links
    if _CALENDAR_PATTERN.search(path):
        return UrlClassification.IGNORED, "calendar_archive_loop"

    # Special files (must check before generic extension checks)
    if path == "/robots.txt" or path.endswith("/robots.txt"):
        return UrlClassification.ROBOTS, "robots_txt"

    if path in ("/sitemap.xml", "/sitemap_index.xml") or path.endswith("/sitemap.xml") or path.endswith("/sitemap_index.xml"):
        return UrlClassification.SITEMAP, "sitemap"

    # API paths and extensions (check before ignored paths)
    for prefix in _API_PATH_PREFIXES:
        if path.startswith(prefix):
            return UrlClassification.API, f"api_path:{prefix}"

    if path == "/graphql" or path.startswith("/graphql/"):
        return UrlClassification.API, "api_path:/graphql"

    for ext in _API_EXTENSIONS:
        if path.endswith(ext):
            return UrlClassification.API, f"api_extension:{ext}"

    # Exact ignored paths
    if path in _IGNORED_PATHS:
        return UrlClassification.IGNORED, f"ignored_path:{path}"

    # Ignored path prefixes
    for prefix in _IGNORED_PATH_PREFIXES:
        if path.startswith(prefix):
            return UrlClassification.IGNORED, f"ignored_path_prefix:{prefix}"

    # Resource extensions
    for ext in _RESOURCE_EXTENSIONS:
        if path.endswith(ext):
            return UrlClassification.RESOURCE, f"resource_extension:{ext}"


    # Query parameter safety checks
    if parsed.query:
        query_params = _extract_query_param_names(parsed.query)
        if len(query_params) > 5:
            return UrlClassification.IGNORED, "too_many_params"
        faceted_count = sum(1 for p in query_params if p.lower() in _FACETED_PARAM_PREFIXES)
        if faceted_count >= 2:
            return UrlClassification.IGNORED, "faceted_url"

    return UrlClassification.HTML, "eligible"


def _extract_query_param_names(query: str) -> list[str]:
    """Extract parameter names from a query string."""
    if not query:
        return []
    return [part.split("=")[0] for part in query.split("&") if "=" in part]


def _is_tracking_param(name: str) -> bool:
    """Check if query parameter is a tracking/session identifier."""
    name_lower = name.lower()
    if name_lower.startswith("utm_"):
        return True
    return name_lower in _TRACKING_PARAMS


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
        if not _is_tracking_param(part.split("=")[0])
    ]
    new_query = "&".join(params)

    return parsed._replace(query=new_query).geturl()



