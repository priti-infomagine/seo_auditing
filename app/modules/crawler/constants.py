"""
Constants used by the crawler module.

Keep this module limited to crawler-wide defaults and protocol-level
configuration. SEO thresholds and rule-engine configuration should not
live here.
"""

DEFAULT_TIMEOUT = 30
DEFAULT_CONCURRENCY = 10
DEFAULT_MAX_DEPTH = 5
DEFAULT_MAX_REDIRECTS = 10

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

CRAWLABLE_SCHEMES = {
    "http",
    "https",
}

SUPPORTED_HTML_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
}

DISCOVERABLE_CONTENT_TYPES = {
    "text/html",
    "application/xhtml+xml",
    "application/xml",
    "text/xml",
}

HTTP_RETRY_STATUS_CODES = {
    408,
    425,
    429,
    500,
    502,
    503,
    504,
}

SECURITY_HEADER_NAMES = {
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
    "cross-origin-opener-policy",
    "cross-origin-resource-policy",
}
IGNORED_URL_SCHEMES = {
    "mailto",
    "tel",
    "javascript",
    "data",
}

__all__ = [
    "DEFAULT_TIMEOUT",
    "DEFAULT_CONCURRENCY",
    "DEFAULT_MAX_DEPTH",
    "DEFAULT_MAX_REDIRECTS",
    "DEFAULT_USER_AGENT",
    "CRAWLABLE_SCHEMES",
    "SUPPORTED_HTML_CONTENT_TYPES",
    "DISCOVERABLE_CONTENT_TYPES",
    "HTTP_RETRY_STATUS_CODES",
    "SECURITY_HEADER_NAMES",
    "IGNORED_URL_SCHEMES",
]


