"""
CoreSEOConfig — self-contained configuration for the Core SEO crawler pipeline.

Mirrors the CrawlConfig pattern from app.modules.crawler.config but
does not import from that module.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

from .constants import (
    DEFAULT_ACCEPT_LANGUAGE,
    DEFAULT_BROWSER_CONCURRENCY,
    DEFAULT_BROWSER_TIMEOUT,
    DEFAULT_CONCURRENCY,
    DEFAULT_CRAWL_DELAY_MS,
    DEFAULT_MAX_DEPTH,
    DEFAULT_MAX_PAGES,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_TIMEOUT,
    DEFAULT_USER_AGENT,
)


@dataclass
class CoreSEOConfig:
    """Configuration for the Core SEO crawler pipeline."""

    max_pages: int = DEFAULT_MAX_PAGES
    max_depth: int = DEFAULT_MAX_DEPTH
    concurrency: int = DEFAULT_CONCURRENCY
    browser_timeout: float = DEFAULT_BROWSER_TIMEOUT
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT
    user_agent: str = DEFAULT_USER_AGENT
    accept_language: str = DEFAULT_ACCEPT_LANGUAGE
    browser_concurrency: int = DEFAULT_BROWSER_CONCURRENCY
    respect_robots: bool = True
    ssrf_protection: bool = True
    crawl_delay_ms: int = DEFAULT_CRAWL_DELAY_MS
    allow_private_ips: bool = False
    viewport_width: int = 1280
    viewport_height: int = 800
    sitemap_timeout: float = DEFAULT_TIMEOUT
    request_delay_ms: int = 0

    def validate(self) -> None:
        """Validate configuration values."""
        assert self.max_pages > 0, "max_pages must be > 0"
        assert self.max_depth >= 0, "max_depth must be >= 0"
        assert self.concurrency > 0, "concurrency must be > 0"
        assert self.browser_concurrency > 0, "browser_concurrency must be > 0"
        assert self.browser_timeout > 0, "browser_timeout must be > 0"
        assert self.request_timeout > 0, "request_timeout must be > 0"
        assert self.crawl_delay_ms >= 0, "crawl_delay_ms must be >= 0"

    @classmethod
    def from_dict(cls, data: dict | None) -> CoreSEOConfig:
        """Construct CoreSEOConfig from a dictionary with fallbacks to settings/defaults."""
        if not data:
            return cls()

        config = cls(
            max_pages=data.get(
                "max_pages",
                min(
                    cls.__dataclass_fields__["max_pages"].default,
                    getattr(settings, "CRAWL_MAX_PAGES", 100),
                ),
            ),
            max_depth=data.get("max_depth", DEFAULT_MAX_DEPTH),
            concurrency=data.get("concurrency", DEFAULT_CONCURRENCY),
            browser_timeout=float(data.get("browser_timeout", DEFAULT_BROWSER_TIMEOUT)),
            request_timeout=float(
                data.get("request_timeout", data.get("timeout_seconds", DEFAULT_REQUEST_TIMEOUT))
            ),
            user_agent=data.get("user_agent") or DEFAULT_USER_AGENT,
            accept_language=data.get("accept_language") or DEFAULT_ACCEPT_LANGUAGE,
            browser_concurrency=int(data.get("browser_concurrency", DEFAULT_BROWSER_CONCURRENCY)),
            respect_robots=data.get("respect_robots", True),
            ssrf_protection=data.get("ssrf_protection", True),
            crawl_delay_ms=int(
                data.get("crawl_delay_ms", data.get("delay_ms", DEFAULT_CRAWL_DELAY_MS))
            ),
            allow_private_ips=data.get("allow_private_ips", False),
            viewport_width=int(data.get("viewport_width", 1280)),
            viewport_height=int(data.get("viewport_height", 800)),
            sitemap_timeout=float(data.get("sitemap_timeout", DEFAULT_TIMEOUT)),
            request_delay_ms=int(data.get("request_delay_ms", DEFAULT_CRAWL_DELAY_MS)),
        )
        config.validate()
        return config


__all__ = ["CoreSEOConfig"]
