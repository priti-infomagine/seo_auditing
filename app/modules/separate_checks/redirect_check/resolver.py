"""Per-run SEO context for the redirect check.

``ResolveContext`` holds the discovery results (sitemap, robots, crawler SEO data and the
link graph) so every checked URL can be enriched with canonical URL, robots.txt allowance,
sitemap membership and source pages. Redirect counting itself lives in
``redirect_report.analyze_result`` (single source of truth).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from protego import Protego

from app.modules.crawler.services.site_discovery_service import SiteDiscoveryResult
from app.shared.utils.url_utils import normalize_url


@dataclass
class ResolveContext:
    """Shared context for resolving redirect results.

    Holds discovery results and pre-fetched SEO data so that the resolver
    does not re-discover the same information for every URL.
    """

    site_discovery: SiteDiscoveryResult
    sitemap_url_set: set[str] = field(default_factory=set)
    url_to_seo: dict[str, dict[str, Any]] = field(default_factory=dict)
    url_to_sources: dict[str, list[str]] = field(default_factory=dict)
    robot_parser: Protego | None = None
    domain: str = ""

    def is_in_sitemap(self, url: str) -> bool:
        normalized = normalize_url(url) if url else ""
        return normalized in self.sitemap_url_set

    def get_seo_data(self, url: str) -> dict[str, Any] | None:
        normalized = normalize_url(url) if url else ""
        return self.url_to_seo.get(normalized)

    def get_source_pages(self, url: str) -> list[str]:
        normalized = normalize_url(url) if url else ""
        return self.url_to_sources.get(normalized, [])

    def robots_allows(self, url: str) -> bool:
        if self.robot_parser is None:
            return True
        try:
            return self.robot_parser.can_fetch(url, "*")   # protego signature: (url, user_agent)
        except Exception:
            return True
