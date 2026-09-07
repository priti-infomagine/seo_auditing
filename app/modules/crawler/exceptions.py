"""
Crawler Exception hierarchy.
Defines structured error types for transport, rendering, robots, SSRF, and extraction failures.
"""
from typing import Optional


class CrawlerError(Exception):
    """Base crawler exception."""

    def __init__(
        self,
        message: str,
        error_type: str = "crawler_error",
        url: Optional[str] = None,
        retryable: bool = False,
    ):
        super().__init__(message)
        self.message = message
        self.error_type = error_type
        self.url = url
        self.retryable = retryable


class SSRFError(CrawlerError):
    """Raised when a URL resolves to a forbidden private IP or internal network."""

    def __init__(self, message: str, url: Optional[str] = None):
        super().__init__(message, error_type="ssrf_blocked", url=url, retryable=False)


class InvalidURLError(CrawlerError):
    """Raised when a URL is invalid or malformed."""

    def __init__(self, message: str, url: Optional[str] = None):
        super().__init__(message, error_type="invalid_url", url=url, retryable=False)


class UnsupportedSchemeError(CrawlerError):
    """Raised when the URL scheme is not supported (e.g. mailto, tel, ftp)."""

    def __init__(self, message: str, url: Optional[str] = None):
        super().__init__(message, error_type="unsupported_scheme", url=url, retryable=False)


class RobotsBlockedError(CrawlerError):
    """Raised when crawling a URL is disallowed by robots.txt."""

    def __init__(self, message: str, url: Optional[str] = None):
        super().__init__(message, error_type="robots_blocked", url=url, retryable=False)


class FetchError(CrawlerError):
    """HTTP fetch transport failure."""

    def __init__(
        self,
        message: str,
        error_type: str = "fetch_error",
        url: Optional[str] = None,
        retryable: bool = True,
    ):
        super().__init__(message, error_type=error_type, url=url, retryable=retryable)


class RenderError(CrawlerError):
    """Playwright browser rendering failure."""

    def __init__(
        self,
        message: str,
        error_type: str = "render_error",
        url: Optional[str] = None,
        retryable: bool = True,
    ):
        super().__init__(message, error_type=error_type, url=url, retryable=retryable)


class ContentTooLargeError(CrawlerError):
    """Raised when response body size exceeds configured limit."""

    def __init__(self, message: str, url: Optional[str] = None):
        super().__init__(message, error_type="content_too_large", url=url, retryable=False)
