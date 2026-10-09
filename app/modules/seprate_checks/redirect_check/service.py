"""Redirect check service — domain-level redirect chain analysis with streaming.

Orchestrates: sitemap/robots discovery → URL collection → per-URL redirect
check (via bulk_status.RedirectCheckerService) → enrichment (via RedirectResolver)
→ SSE event streaming → analysis/evaluation → persistence.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable
from typing import Any
from urllib.parse import urlparse

from protego import Protego
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logger import logger
from app.modules.crawler.models.crawl_pages import CrawlPage
from app.modules.crawler.models.page_seo_data import PageSEOData
from app.modules.crawler.services.site_discovery_service import (
    RobotsTxtEvidence,
    SiteDiscoveryResult,
    SiteDiscoveryService,
)
from app.modules.seprate_checks.bulk_status.schema import (
    RedirectCheckRequest as BulkRedirectCheckRequest,
)
from app.modules.seprate_checks.bulk_status.service import RedirectCheckerService
from app.modules.seprate_checks.link_analysis.crawler import SiteCrawler
from app.modules.streaming_audit.config import STREAMING_AUDIT_MAX_CONCURRENCY
from app.modules.streaming_audit.models.streaming_audit_run import StreamingAuditStatus
from app.modules.streaming_audit.services.streaming_audit_service import (
    StreamingAuditService,
    normalize_url,
)
from app.shared.utils.url_utils import normalize_host

from .analyzer import RedirectCheckAnalyzer
from .resolver import RedirectResolver, ResolveContext
from .schema import RedirectUrlResult
from .streaming_adapter import StreamingRedirectAdapter


class RedirectCheckService:
    """Domain-level redirect checker integrating with streaming_audit pipeline."""

    def __init__(self, redis: Any | None = None):
        self.redis = redis

    @staticmethod
    def _normalize_domain(raw_domain: str) -> tuple[str, str]:
        """Normalize input into (canonical_url, domain)."""
        cleaned = raw_domain.strip()
        if not cleaned:
            raise ValueError("domain must not be empty")
        if not cleaned.startswith(("http://", "https://")):
            cleaned = f"https://{cleaned}"
        parsed = urlparse(cleaned)
        host = normalize_host(parsed.netloc) or ""
        if not host:
            raise ValueError(f"Invalid domain provided: {raw_domain}")
        if "." not in host:
            raise ValueError(f"Domain must include a valid TLD: {raw_domain}")
        canonical_url = f"{parsed.scheme or 'https'}://{parsed.netloc}"
        return canonical_url, host

    @classmethod
    async def prepare_check(
        cls,
        domain: str,
        db: AsyncSession,
        max_urls: int = 500,
    ) -> str:
        """Validate input and create a StreamingAuditRun record. Returns audit_id."""
        canonical_url, normalized_domain = cls._normalize_domain(domain)
        service = StreamingAuditService(db)
        run = await service.create_run(
            seed_url=canonical_url,
            max_pages=max_urls,
            config={"redirect_check": True, "domain": normalized_domain},
        )
        await service.update_run(run.id, domain=normalized_domain)
        return str(run.id)

    async def discover_urls(
        self,
        domain: str,
        max_urls: int,
    ) -> tuple[list[str], SiteDiscoveryResult, Protego | None, Any]:
        """Discover all checkable URLs for the domain.

        Combines sitemap URLs with crawled internal page URLs.
        Returns (deduplicated_url_list, site_discovery_result, robot_parser, crawl_result).
        """
        canonical_url, normalized_domain = self._normalize_domain(domain)

        logger.info("RedirectCheckService: starting URL discovery for %s", canonical_url)

        discovery = SiteDiscoveryService(
            canonical_url,
            timeout=int(settings.LINK_ANALYSIS_PAGE_TIMEOUT),
            max_child_sitemaps=40,
            max_urls_per_sitemap=5000,
            max_total_page_urls=settings.LINK_ANALYSIS_MAX_PAGES,
        )
        try:
            site_result: SiteDiscoveryResult = await asyncio.wait_for(
                discovery.discover(),
                timeout=settings.LINK_ANALYSIS_PAGE_TIMEOUT * 5,
            )
        except Exception as exc:
            logger.warning("RedirectCheckService: discovery failed for %s: %s", domain, exc)
            site_result = SiteDiscoveryResult(
                robots=RobotsTxtEvidence(url=f"{canonical_url}/robots.txt", exists=False),
            )

        sitemap_urls: set[str] = set()
        for sm in site_result.sitemaps:
            for u in sm.urls or []:
                try:
                    norm = normalize_url(u)
                    if norm:
                        sitemap_urls.add(norm)
                except Exception:
                    pass
            for child in sm.child_sitemaps or []:
                try:
                    norm = normalize_url(child)
                    if norm:
                        sitemap_urls.add(norm)
                except Exception:
                    pass

        logger.info(
            "RedirectCheckService: discovery complete — sitemaps=%d, robots_exists=%s, sitemap_urls=%d",
            len(site_result.sitemaps),
            site_result.robots.exists,
            len(sitemap_urls),
        )

        crawler = SiteCrawler(
            canonical_url=canonical_url,
            domain=normalized_domain,
            max_pages=max_urls,
        )
        crawl_result: Any = None
        try:
            crawl_result = await crawler.crawl()
        except Exception as exc:
            logger.warning("RedirectCheckService: crawl failed for %s: %s", domain, exc)
        finally:
            if crawler._page_crawler is not None:
                try:
                    await crawler._page_crawler.http_fetcher.close()
                except Exception:
                    pass
                crawler._page_crawler = None

        all_urls: list[str] = list(sitemap_urls)

        if crawl_result:
            for page_url in crawl_result.graph.pages:
                if page_url not in sitemap_urls:
                    all_urls.append(page_url)
            for url in crawl_result.sitemap_urls:
                try:
                    norm_url = normalize_url(url)
                    if norm_url and norm_url not in sitemap_urls:
                        all_urls.append(norm_url)
                except Exception:
                    pass

        all_urls = all_urls[:max_urls]

        logger.info(
            "RedirectCheckService: discovered %d total URLs (sitemap=%d, crawl=%d)",
            len(all_urls), len(sitemap_urls), len(all_urls) - len(sitemap_urls),
        )
        print(f"[redirect-check] Discovered {len(all_urls)} URLs for {domain}", flush=True)

        robot_parser: Protego | None = None
        if site_result.robots.exists and site_result.robots.content:
            try:
                robot_parser = Protego.parse(site_result.robots.content)
            except Exception as exc:
                logger.warning("RedirectCheckService: failed to parse robots.txt: %s", exc)

        return all_urls, site_result, robot_parser, crawl_result

    async def _build_seo_map(
        self,
        db: AsyncSession,
        audit_id: str,
    ) -> dict[str, dict[str, Any]]:
        """Query PageSEOData + CrawlPage for the given audit_id, keyed by normalized URL."""
        audit_uuid = uuid.UUID(str(audit_id))
        page_rows = (
            await db.execute(
                select(CrawlPage).where(CrawlPage.audit_id == audit_uuid)
            )
        ).scalars().all()

        if not page_rows:
            return {}

        page_ids = [p.id for p in page_rows]
        seo_rows = (
            await db.execute(
                select(PageSEOData).where(PageSEOData.page_id.in_(page_ids))
            )
        ).scalars().all()
        seo_by_page = {row.page_id: row for row in seo_rows}

        url_to_seo: dict[str, dict[str, Any]] = {}
        for page in page_rows:
            try:
                norm = normalize_url(page.final_url or page.url)
                if not norm:
                    continue
                seo = seo_by_page.get(page.id)
                if seo:
                    url_to_seo[norm] = {
                        "title": seo.title,
                        "meta_description": seo.meta_description,
                        "canonical": seo.canonical,
                        "robots_meta": seo.robots_meta,
                        "page_metadata": seo.page_metadata or {},
                    }
            except Exception:
                pass

        return url_to_seo

    @staticmethod
    def _build_source_map(crawl_result: Any) -> dict[str, list[str]]:
        """Build a map of target_url -> source_pages from the link graph."""
        if crawl_result is None:
            return {}

        source_map: dict[str, list[str]] = {}
        graph = crawl_result.graph

        for source_url, targets in graph.edges_by_source.items():
            for target_url in targets:
                try:
                    norm_target = normalize_url(target_url)
                    if norm_target:
                        source_map.setdefault(norm_target, [])
                        if source_url not in source_map[norm_target]:
                            source_map[norm_target].append(source_url)
                except Exception:
                    pass

        return source_map

    @staticmethod
    def _build_sitemap_url_set(site_result: SiteDiscoveryResult) -> set[str]:
        """Extract all normalized URLs from discovered sitemaps."""
        url_set: set[str] = set()
        for sm in site_result.sitemaps:
            for u in sm.urls or []:
                try:
                    norm = normalize_url(u)
                    if norm:
                        url_set.add(norm)
                except Exception:
                    pass
        return url_set

    def _build_context(
        self,
        domain: str,
        site_result: SiteDiscoveryResult,
        robot_parser: Protego | None,
        seo_map: dict[str, dict[str, Any]],
        source_map: dict[str, list[str]],
    ) -> ResolveContext:
        """Build the ResolveContext shared across all URL resolutions."""
        return ResolveContext(
            site_discovery=site_result,
            sitemap_url_set=self._build_sitemap_url_set(site_result),
            url_to_seo=seo_map,
            url_to_sources=source_map,
            robot_parser=robot_parser,
            domain=domain,
        )

    async def run_check_async(
        self,
        audit_id: str,
        domain: str,
        db: AsyncSession | None = None,
        update_state: Callable[[str, dict | None], None] | None = None,
        max_urls: int = 500,
    ) -> dict[str, Any]:
        """Execute the full domain redirect check workflow.

        Phases: discover → check → enrich → stream → evaluate → persist.
        """
        start_time = time.perf_counter()

        if update_state:
            update_state("PROGRESS", {"phase": "discovery", "message": f"Discovering URLs for {domain}..."})

        urls, site_result, robot_parser, crawl_result = await self.discover_urls(
            domain, max_urls
        )

        if db is not None:
            return await self._execute(
                audit_id, domain, db, urls, site_result, robot_parser,
                crawl_result, update_state, start_time,
            )

        async with async_session_factory() as session:
            try:
                result = await self._execute(
                    audit_id, domain, session, urls, site_result, robot_parser,
                    crawl_result, update_state, start_time,
                )
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def _execute(
        self,
        audit_id: str,
        domain: str,
        db: AsyncSession,
        urls: list[str],
        site_result: SiteDiscoveryResult,
        robot_parser: Protego | None,
        crawl_result: Any,
        update_state: Callable[[str, dict | None], None] | None,
        start_time: float,
    ) -> dict[str, Any]:
        """Execute the check on an active DB session."""
        svc = StreamingAuditService(db)
        adapter = StreamingRedirectAdapter()
        checker = RedirectCheckerService()
        resolver = RedirectResolver()

        await svc.update_run(
            audit_id,
            status=StreamingAuditStatus.PROCESSING,
        )
        await adapter.clear_event_store(audit_id)

        logger.info("RedirectCheckService: starting URL checks for audit_id=%s, urls=%d", audit_id, len(urls))

        if update_state:
            update_state("PROGRESS", {
                "phase": "discovered",
                "message": f"Discovered {len(urls)} URLs for {domain}",
                "total_urls": len(urls),
                "processed": 0,
            })

        await adapter.publish_event(
            audit_id,
            "discovery_complete",
            {
                "total_urls": len(urls),
                "domain": domain,
                "sitemaps_found": len(site_result.sitemaps),
                "robots_exists": site_result.robots.exists,
            },
        )

        seo_map = await self._build_seo_map(db, audit_id)
        source_map = self._build_source_map(crawl_result)
        context = self._build_context(domain, site_result, robot_parser, seo_map, source_map)

        results: list[RedirectUrlResult] = []
        processed = 0
        failed_count = 0
        semaphore = asyncio.Semaphore(STREAMING_AUDIT_MAX_CONCURRENCY)

        async def _check_single(url: str) -> RedirectUrlResult | None:
            nonlocal processed, failed_count
            acquired = False
            async with semaphore:
                acquired = await adapter.reserve_slot(audit_id, limit=STREAMING_AUDIT_MAX_CONCURRENCY)
                try:
                    req = BulkRedirectCheckRequest(mode="urls", urls=[url], max_urls=1)
                    response = await checker.check(req)

                    if response.data.results:
                        raw_result = response.data.results[0]
                        resolved = resolver.resolve(url, raw_result, context)
                    else:
                        resolved = RedirectUrlResult(
                            url=url,
                            error="No result returned",
                            in_sitemap=context.is_in_sitemap(url),
                            robots_allowed=context.robots_allows(url),
                            source_pages=context.get_source_pages(url),
                        )

                    await svc.upsert_page_result(
                        audit_id=audit_id,
                        normalized_url=resolved.url,
                        canonical_url=resolved.canonical,
                        processing_status="completed" if not resolved.error else "failed",
                        http_status=resolved.final_status,
                        page_score=None,
                        processing_latency_ms=0,
                        parsed_payload=None,
                        page_findings={
                            "redirect_count": resolved.redirect_count,
                            "final_url": resolved.final_url,
                            "final_status": resolved.final_status,
                            "error": resolved.error,
                            "is_redirect": resolved.is_redirect,
                            "is_internal_redirect": resolved.is_internal_redirect,
                            "is_external_redirect": resolved.is_external_redirect,
                            "redirects": len(resolved.hops),
                        },
                        discovered_urls=[],
                        error_info=resolved.error,
                    )

                    processed += 1

                    await adapter.publish_event(
                        audit_id,
                        "url_checked",
                        {
                            "url": resolved.url,
                            "redirect_count": resolved.redirect_count,
                            "final_url": resolved.final_url,
                            "final_status": resolved.final_status,
                            "error": resolved.error,
                            "hops": [
                                h.model_dump(by_alias=True, exclude_none=True)
                                for h in resolved.hops
                            ],
                            "chain": resolved.chain,
                            "processed": processed,
                            "total": len(urls),
                        },
                    )

                    if update_state:
                        update_state("PROGRESS", {
                            "phase": "checking",
                            "message": f"Checked {processed}/{len(urls)} URLs",
                            "processed": processed,
                            "total": len(urls),
                        })

                    if resolved.error:
                        failed_count += 1
                    results.append(resolved)
                    return resolved

                except Exception as exc:
                    logger.warning("RedirectCheckService: error checking %s: %s", url, exc)
                    failed_count += 1
                    processed += 1
                    return None
                finally:
                    if acquired:
                        await adapter.release_slot(audit_id)

        tasks = [asyncio.create_task(_check_single(url)) for url in urls]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for item in completed:
            if isinstance(item, Exception):
                logger.warning("RedirectCheckService: task error: %s", item)

        outcome = RedirectCheckAnalyzer.analyze(results, domain)
        cost_seconds = round(time.perf_counter() - start_time, 3)

        logger.info(
            "RedirectCheckService: analysis complete audit_id=%s total=%d findings=%d status=%s",
            audit_id, len(results), len(outcome.findings), outcome.overall_status,
        )

        await svc.update_run(
            audit_id,
            status=StreamingAuditStatus.COMPLETED,
            completed_count=len(results) - failed_count,
            failed_count=failed_count,
            final_summary={
                "total_checked": len(results),
            "redirect_results": [
                {
                    "url": r.url,
                    "redirects": r.redirects,
                    "redirect_count": r.redirect_count,
                    "final_url": r.final_url,
                    "final_status": r.final_status,
                    "error": r.error,
                    "is_redirect": r.is_redirect,
                    "is_internal_redirect": r.is_internal_redirect,
                    "is_external_redirect": r.is_external_redirect,
                    "is_broken": r.is_broken,
                    "canonical": r.canonical,
                    "meta_refresh": r.meta_refresh,
                    "robots_allowed": r.robots_allowed,
                    "in_sitemap": r.in_sitemap,
                    "source_pages": r.source_pages,
                    "hops": [h.model_dump(by_alias=True, exclude_none=True) for h in r.hops],
                    "chain": r.chain,
                }
                for r in results
            ],
                "summary": outcome.summary.model_dump(),
                "findings": [f.model_dump() for f in outcome.findings],
                "recommendations": [r.model_dump() for r in outcome.recommendations],
                "overall_status": outcome.overall_status,
                "severity": outcome.severity,
                "cost_seconds": cost_seconds,
            },
        )

        await adapter.publish_event(
            audit_id,
            "completed",
            {
                "total_checked": len(results),
                "summary": outcome.summary.model_dump(),
                "overall_status": outcome.overall_status,
                "severity": outcome.severity,
                "cost_seconds": cost_seconds,
                "findings_count": len(outcome.findings),
            },
        )

        await adapter.close()

        return {
            "status": "completed",
            "audit_id": audit_id,
            "domain": domain,
            "total_checked": len(results),
            "total_findings": len(outcome.findings),
            "cost_seconds": cost_seconds,
        }
