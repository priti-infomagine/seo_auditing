"""Constants for the redirect_check module."""
from __future__ import annotations

from app.core.config import settings

USER_AGENT = settings.LINK_CHECK_USER_AGENT if hasattr(settings, "LINK_CHECK_USER_AGENT") else (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.3"
)

REDIRECT_STATUSES = {301, 302, 303, 307, 308}
MAX_REDIRECTS = settings.LINK_ANALYSIS_MAX_REDIRECT_HOPS
CHECK_TIMEOUT = settings.LINK_CHECK_TIMEOUT
MAX_CONCURRENCY = settings.LINK_CHECK_MAX_CONCURRENCY
PER_HOST_CONCURRENCY = settings.LINK_ANALYSIS_PER_HOST_CONCURRENCY

MAX_URLS_CAP = 500
REDIS_RESULT_TTL_SECONDS = 3600

RECOMMENDATION_CATALOG: dict[str, dict] = {
    "redirect_internal": {
        "title": "Update internal links to final URL",
        "priority": "low",
        "where_to_fix": "source_pages",
    },
    "redirect_external": {
        "title": "Update external links to final destination",
        "priority": "low",
        "where_to_fix": "source_pages",
    },
    "redirect_chain_long": {
        "title": "Shorten redirect chains",
        "priority": "medium",
        "where_to_fix": "server_config",
    },
    "redirect_loop": {
        "title": "Fix redirect loop",
        "priority": "high",
        "where_to_fix": "server_config",
    },
    "broken_link": {
        "title": "Fix or remove broken link destination",
        "priority": "high",
        "where_to_fix": "server_config",
    },
    "meta_refresh_redirect": {
        "title": "Replace meta refresh with HTTP 301 redirect",
        "priority": "low",
        "where_to_fix": "cms",
    },
    "insecure_redirect": {
        "title": "Avoid redirecting from HTTPS to HTTP",
        "priority": "medium",
        "where_to_fix": "server_config",
    },
}
