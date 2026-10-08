"""Redirect resolution and enrichment for a single checked URL.

The resolver takes a already-checked ``RedirectResult`` (from the existing
``bulk_status.RedirectCheckerService``) and enriches it with SEO context:
canonical URL, meta-refresh, robots.txt allowance, sitemap membership, and
source pages from the link graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from protego import Protego

from app.core.logger import logger
from app.modules.crawler.services.site_discovery_service import SiteDiscoveryResult
from app.shared.utils.url_utils import is_same_site, normalize_host, normalize_url

from .schema import RedirectHop, RedirectUrlResult


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
            return self.robot_parser.can_fetch("*", url)
        except Exception:
            return True


class RedirectResolver:
    """Enriches redirect check results with SEO context."""

    @staticmethod
    def _classify_redirect(final_url: str | None, domain: str) -> tuple[bool, bool]:
        """Classify redirect as internal or external relative to *domain*."""
        if not final_url:
            return False, False
        try:
            from urllib.parse import urlparse

            parsed = urlparse(final_url)
            final_host = normalize_host(parsed.netloc) or ""
            if final_host:
                is_external = not (
                    final_host == domain or is_same_site(parsed.netloc, domain)
                )
                return not is_external, is_external
        except Exception:
            pass
        return False, False

    @staticmethod
    def _extract_hops(hops: list[Any]) -> list[RedirectHop]:
        """Convert raw hop dicts/objects to RedirectHop schema objects."""
        result: list[RedirectHop] = []
        for hop in hops:
            if hasattr(hop, "model_dump"):
                hop_dict = hop.model_dump(by_alias=True)
            elif isinstance(hop, dict):
                hop_dict = hop
            else:
                continue
            result.append(
                RedirectHop(
                    url=hop_dict.get("url", ""),
                    status=hop_dict.get("status"),
                    status_text=hop_dict.get("statusText"),
                    location=hop_dict.get("location"),
                    resolved=hop_dict.get("resolved"),
                    latency_ms=hop_dict.get("latencyMs"),
                    headers=hop_dict.get("headers", []),
                )
            )
        return result

    @staticmethod
    def _build_chain(hops: list[Any]) -> list[dict[str, Any]]:
        """Build a lightweight redirect chain summary for API response."""
        chain: list[dict[str, Any]] = []
        for hop in hops:
            if hasattr(hop, "model_dump"):
                hop_dict = hop.model_dump(by_alias=True)
            elif isinstance(hop, dict):
                hop_dict = hop
            else:
                continue
            chain.append(
                {
                    "url": hop_dict.get("url", ""),
                    "status": hop_dict.get("status"),
                    "location": hop_dict.get("location"),
                    "resolved": hop_dict.get("resolved"),
                    "latency_ms": hop_dict.get("latencyMs"),
                }
            )
        return chain

    @classmethod
    def resolve(
        cls,
        url: str,
        check_result: Any,
        context: ResolveContext,
    ) -> RedirectUrlResult:
        """Resolve a single URL's redirect check result into a enriched schema object.

        Args:
            url: The original input URL.
            check_result: A ``RedirectResult`` (pydantic model) from
                ``RedirectCheckerService.check()``.
            context: Shared ``ResolveContext`` with discovery + SEO data.

        Returns:
            ``RedirectUrlResult`` with hops, final URL/status, enrichment
            flags, and source pages.
        """
        raw = check_result.model_dump(by_alias=True) if hasattr(check_result, "model_dump") else dict(check_result)

        hops = cls._extract_hops(raw.get("hops", []))
        chain = cls._build_chain(raw.get("hops", []))
        redirect_count = raw.get("redirects", 0) or len(hops)
        is_redirect = redirect_count > 0
        final_url = raw.get("finalUrl") or raw.get("final_url")
        final_status = raw.get("finalStatus") or raw.get("final_status")
        error = raw.get("error")

        logger.debug(
            "RedirectResolver: resolving url=%s redirect_count=%s final_url=%s final_status=%s error=%s",
            url, redirect_count, final_url, final_status, error,
        )

        is_internal, is_external = cls._classify_redirect(final_url, context.domain)

        seo_data = context.get_seo_data(url)
        canonical = seo_data.get("canonical") if seo_data else None
        meta_refresh = None
        if seo_data:
            metadata = seo_data.get("page_metadata", {}) or {}
            meta_refresh = metadata.get("meta_refresh")

        is_broken = bool(error)
        if final_status is not None:
            is_broken = is_broken or final_status >= 400
            if final_status == 0 and error:
                is_broken = True

        return RedirectUrlResult(
            url=url,
            hops=hops,
            redirects=redirect_count,
            final_url=final_url,
            final_status=final_status,
            error=error,
            redirect_count=redirect_count,
            chain=chain,
            is_redirect=is_redirect,
            is_internal_redirect=is_internal if is_redirect else False,
            is_external_redirect=is_external if is_redirect else False,
            is_broken=is_broken,
            canonical=canonical,
            meta_refresh=meta_refresh,
            robots_allowed=context.robots_allows(url),
            in_sitemap=context.is_in_sitemap(url),
            source_pages=context.get_source_pages(url),
        )
