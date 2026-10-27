"""
Shared exception types for all non-auth modules of the SSEO Analyzer.

These exceptions follow a fault-tolerant design:
- Non-fatal errors (parser failures, rule failures, missing data) are caught
  at the call site and logged, allowing the pipeline to continue.
- Fatal system-level errors (database unreachable, crawl not found) propagate
  to fail the entire operation.

Auth module is explicitly excluded from this pattern — auth failures
should raise 401/403.

Error categorization:
- ``SitemapCheckError`` and ``categorize_error`` help background-check
  modules convert raw infrastructure exceptions (asyncio event-loop
  conflicts, network timeouts, etc.) into structured ``(error_code,
  user_message)`` tuples that can be stored in the DB and surfaced to
  the UI with an appropriate HTTP status code.
"""
from __future__ import annotations

import asyncio

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is a hard dependency
    httpx = None  # type: ignore[assignment]

try:
    import aiohttp
except ImportError:  # pragma: no cover
    aiohttp = None  # type: ignore[assignment]


class SSEOAnalyzerError(Exception):
    """Base exception for all non-auth modules of the SSEO Analyzer."""


class ParserError(SSEOAnalyzerError):
    """Raised when page parsing fails (non-fatal — pipeline continues)."""


class RuleEvaluationError(SSEOAnalyzerError):
    """Raised when a single rule evaluation fails (non-fatal)."""


class ScoringError(SSEOAnalyzerError):
    """Raised when score calculation fails for a page or project (non-fatal)."""


class DatabaseError(SSEOAnalyzerError):
    """Raised on database operation failures (system-level)."""


class SitemapCheckError(Exception):
    """Raised when a sitemap check fails and the error has been categorized.

    Carries an ``error_code`` (machine-readable) and a ``user_message``
    (human-readable, safe to return to the UI) alongside the original
    exception for debugging.
    """

    def __init__(
        self,
        error_code: str,
        user_message: str,
        original_exc: Exception | None = None,
    ) -> None:
        self.error_code = error_code
        self.user_message = user_message
        self.original_exc = original_exc
        super().__init__(user_message)


HTTP_STATUS_BY_ERROR_CODE = {
    "event_loop_conflict": 502,
    "timeout": 504,
    "network_error": 502,
    "sitemap_fetch_error": 502,
    "sitemap_parse_error": 422,
    "internal_error": 500,
}

# User-friendly messages keyed by error_code
USER_FRIENDLY_MESSAGES: dict[str, str] = {
    "event_loop_conflict": (
        "Internal error: the background check encountered an event-loop "
        "conflict. Please retry the check."
    ),
    "timeout": (
        "The check timed out while contacting the target website. "
        "The site may be slow or unreachable."
    ),
    "network_error": (
        "Network error: unable to reach the target website. "
        "Please verify the URL is correct and the site is online."
    ),
    "sitemap_fetch_error": (
        "Failed to fetch sitemap data from the target website."
    ),
    "sitemap_parse_error": (
        "Failed to parse sitemap data from the target website."
    ),
    "internal_error": (
        "An internal error occurred during the sitemap check."
    ),
}


def categorize_error(exc: Exception) -> tuple[str, str]:
    """Convert an exception into ``(error_code, user_message)``.

    The categorization is intentionally broad so it is reusable across
    every background-check module (sitemap, serp_rank, meta_check, etc.).
    The *full* original exception should still be logged separately with
    ``exc_info=True`` for debugging.
    """
    exc_type = type(exc).__name__
    exc_str = str(exc)

    # --- asyncio event-loop conflicts (Celery + async DB pattern) ---
    if "attached to a different loop" in exc_str:
        return (
            "event_loop_conflict",
            USER_FRIENDLY_MESSAGES["event_loop_conflict"],
        )

    # --- Timeouts ---
    timeout_types = (
        "TimeoutError",
        "asyncio.TimeoutError",
        "asyncio.exceptions.TimeoutError",
        "ConnectTimeout",
        "ReadTimeout",
        "WriteTimeout",
        "PoolTimeout",
    )
    if any(t in exc_type for t in timeout_types) or (
        "timeout" in exc_str.lower() and "timed out" in exc_str.lower()
    ):
        return (
            "timeout",
            USER_FRIENDLY_MESSAGES["timeout"],
        )

    # --- Network / connection errors ---
    network_types = (
        "ConnectionError",
        "ConnectError",
        "ClientConnectorError",
        "ServerNotFoundError",
        "ClientError",
        "ServerDisconnectedError",
        "ProxyError",
        "ConnectTimeout",
        "ReadTimeout",
    )
    network_keywords = ("unreachable", "connection refused", "connection reset",
                        "name or service not known", "network is unreachable",
                        "connection timed out", "dns", "no route to host")
    if _is_httpx_network_error(exc) or any(
        t in exc_type for t in network_types
    ) or any(k in exc_str.lower() for k in network_keywords):
        return (
            "network_error",
            USER_FRIENDLY_MESSAGES["network_error"],
        )

    # --- sitemap-specific parse errors (from _fetch_sitemap) ---
    if "Sitemap XML could not be parsed" in exc_str or "XML" in exc_str:
        return (
            "sitemap_parse_error",
            USER_FRIENDLY_MESSAGES["sitemap_parse_error"],
        )

    # --- Fallback — truncate the raw message for the UI ---
    safe_msg = exc_str.strip()
    if len(safe_msg) > 500:
        safe_msg = safe_msg[:500] + "... [truncated]"
    if not safe_msg:
        safe_msg = USER_FRIENDLY_MESSAGES["internal_error"]
    return "internal_error", safe_msg


def _is_httpx_network_error(exc: Exception) -> bool:
    """Return True if *exc* is an httpx transport-level error."""
    if httpx is None:
        return False
    return isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.ConnectTimeout,
            httpx.WriteTimeout,
            httpx.NetworkError,
            httpx.RemoteProtocolError,
        ),
    )


__all__ = [
    "SSEOAnalyzerError",
    "ParserError",
    "RuleEvaluationError",
    "ScoringError",
    "DatabaseError",
    "SitemapCheckError",
    "HTTP_STATUS_BY_ERROR_CODE",
    "USER_FRIENDLY_MESSAGES",
    "categorize_error",
]
