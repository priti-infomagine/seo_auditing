"""
Crawler configuration module.
Defines CrawlConfig dataclass with strict validation.
"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CrawlConfig:
    max_pages: int = 1000
    max_depth: int = 5

    http_concurrency: int = 20
    browser_concurrency: int = 3

    request_timeout: float = 30.0
    browser_timeout: float = 45.0

    max_redirects: int = 10
    max_response_size: int = 10 * 1024 * 1024  # 10 MB

    respect_robots: bool = True
    enable_browser_rendering: bool = True
    render_fallback_enabled: bool = True

    crawl_delay_ms: int = 0
    verify_resources: bool = False

    user_agent: str = (
        "Mozilla/5.0 (compatible; SEOAuditBot/1.0; +http://seoaudit.local/bot)"
    )
    accept_language: str = "en-US,en;q=0.9"

    allow_private_ips: bool = False  # SSRF protection toggle

    def validate(self) -> None:
        """Validate configuration values."""
        if self.max_pages <= 0:
            raise ValueError("max_pages must be > 0")
        if self.max_depth < 0:
            raise ValueError("max_depth must be >= 0")
        if self.http_concurrency <= 0:
            raise ValueError("http_concurrency must be > 0")
        if self.browser_concurrency <= 0:
            raise ValueError("browser_concurrency must be > 0")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be > 0")
        if self.browser_timeout <= 0:
            raise ValueError("browser_timeout must be > 0")
        if self.max_redirects < 0:
            raise ValueError("max_redirects must be >= 0")

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "CrawlConfig":
        """Construct CrawlConfig from a dictionary with fallbacks."""
        if not data:
            return cls()

        concurrency = data.get("concurrency")
        http_conc = data.get("http_concurrency", concurrency or 20)
        browser_conc = data.get("browser_concurrency", 3)

        config = cls(
            max_pages=data.get("max_pages", 1000),
            max_depth=data.get("max_depth", 5),
            http_concurrency=int(http_conc),
            browser_concurrency=int(browser_conc),
            request_timeout=float(data.get("request_timeout", data.get("timeout_seconds", 30.0))),
            browser_timeout=float(data.get("browser_timeout", 45.0)),
            max_redirects=data.get("max_redirects", 10),
            max_response_size=data.get("max_response_size", 10 * 1024 * 1024),
            respect_robots=data.get("respect_robots", True),
            enable_browser_rendering=data.get("enable_browser_rendering", True),
            render_fallback_enabled=data.get("render_fallback_enabled", True),
            crawl_delay_ms=data.get("delay_ms", data.get("crawl_delay_ms", 0)),
            verify_resources=data.get("verify_resources", False),
            user_agent=data.get("user_agent") or cls.user_agent,
            accept_language=data.get("accept_language") or cls.accept_language,
            allow_private_ips=data.get("allow_private_ips", False),
        )
        config.validate()
        return config
