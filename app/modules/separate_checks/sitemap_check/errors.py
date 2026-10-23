"""
Shared error types for sitemap availability checks.

Raised by the sitemap-required gate in the ``/audit/analyze`` and
``/core-seo/crawl`` pipelines when live sitemap discovery finds no usable
sitemap for the requested domain.
"""
from __future__ import annotations

NO_SITEMAP_MESSAGE = "no sitemap found, build first"


class NoSitemapAvailableError(Exception):
    """Raised when a live sitemap check finds no usable sitemap for a domain."""

    def __init__(self, message: str = NO_SITEMAP_MESSAGE) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = 404


__all__ = ["NoSitemapAvailableError", "NO_SITEMAP_MESSAGE"]
