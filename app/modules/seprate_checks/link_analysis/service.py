"""Link analysis service — thin orchestration layer.

Coordinates: site discovery -> crawl -> link check -> analyze -> persist.
All business logic lives in analyzer.py, crawler.py, link_checker.py.
This module handles only sequencing and transactions.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Dict, List, Optional, Set
from urllib.parse import urlparse
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.core.logger import logger

from .analyzer import (
    FindingCandidate,
    analyze,
    analyze_optimization,
    compute_overall_status,
    compute_summary,
)
from .crawler import CrawlResult, SiteCrawler
from .graph import CheckResult
from .link_checker import LinkChecker
from .model import (
    FindingType,
    LinkAnalysisCheck,
    LinkAnalysisCheckStatus,
    LinkAnalysisSeverity,
    LinkAnalysisOverallStatus,
    LinkFinding,
    FindingCategory,
)
from .recommendations import build_recommendation
from .repository import LinkAnalysisRepository
from app.shared.utils.url_utils import normalize_host, normalize_url


def _normalize_target_url(raw_url: str) -> str:
    cleaned = raw_url.strip()
    if not cleaned.startswith(("http://", "https://")):
        cleaned = f"https://{cleaned}"
    parsed = urlparse(cleaned)
    host = parsed.hostname or ""
    if not host:
        raise ValueError(f"Invalid URL or domain provided: {raw_url}")
    path = parsed.path or "/"
    if parsed.query:
        path = f"{path}?{parsed.query}"
    canonical = f"{parsed.scheme or 'https'}://{parsed.netloc}{path}"
    return canonical


def _candidate_to_finding_row(
    check_id: UUID,
    candidate: FindingCandidate,
) -> LinkFinding:
    """Convert a FindingCandidate to a LinkFinding DB model."""
    ft = candidate.type.value if hasattr(candidate.type, "value") else candidate.type
    cat = candidate.category.value if hasattr(candidate.category, "value") else candidate.category
    sev = candidate.severity.value if hasattr(candidate.severity, "value") else candidate.severity

    evidence: Dict[str, Any] = {}
    if candidate.extra:
        evidence.update(candidate.extra)
    if candidate.error_type:
        evidence["error_type"] = candidate.error_type
    if candidate.status_code is not None:
        evidence["status_code"] = candidate.status_code
    if candidate.final_url:
        evidence["final_url"] = candidate.final_url

    sources_data = [
        {"source_url": s.source_url, "anchor_text": s.anchor_text, "rel": s.rel}
        for s in candidate.sources[: settings.LINK_ANALYSIS_EVIDENCE_SOURCE_CAP]
    ]
    evidence["sources"] = sources_data
    evidence["total_sources"] = len(candidate.sources)

    rec = build_recommendation(candidate)

    return LinkFinding(
        check_id=check_id,
        category=cat,
        type=ft,
        severity=sev,
        target_url=candidate.target_url,
        status_code=candidate.status_code,
        final_url=candidate.final_url,
        evidence=evidence,
        recommendation=rec,
    )


class LinkAnalysisService:
    """Service to execute async link analysis crawl jobs."""

    def __init__(self, redis: Optional[Redis] = None):
        self.redis = redis

    @classmethod
    async def prepare_check(
        cls,
        url: str,
        db: AsyncSession,
        redis: Optional[Redis] = None,
        max_pages: Optional[int] = None,
    ) -> LinkAnalysisCheck:
        """Validate input and create initial queued record in DB."""
        canonical_url = _normalize_target_url(url)
        parsed = urlparse(canonical_url)
        domain = normalize_host(parsed.netloc) or ""

        progress_payload: Dict[str, Any] = {
            "phase": "queued",
            "message": "Check queued in worker",
        }
        if max_pages is not None:
            progress_payload["max_pages"] = max_pages

        check = LinkAnalysisCheck(
            url=canonical_url,
            domain=domain,
            status=LinkAnalysisCheckStatus.QUEUED.value,
            progress=progress_payload,
        )
        repo = LinkAnalysisRepository(db, redis=redis)
        saved = await repo.create(check)
        await db.commit()
        await db.refresh(saved)
        await repo.set_status(
            check_id=saved.id,
            status=LinkAnalysisCheckStatus.QUEUED,
            progress=progress_payload,
        )
        return saved

    def _progress_callback(self, check_id: UUID, db_session: AsyncSession) -> Callable:
        """Create a callback that writes progress to DB + Redis."""
        repo = LinkAnalysisRepository(db_session, redis=self.redis)

        async def _do_update(phase: str, pages: int, discovered: int):
            await repo.update_progress(
                check_id,
                LinkAnalysisCheckStatus.PROCESSING,
                progress={
                    "phase": phase,
                    "pages_crawled": pages,
                    "total_discovered": discovered,
                },
            )

        def _callback(phase: str, pages: int, discovered: int):
            try:
                loop = asyncio.get_running_loop()
                asyncio.ensure_future(_do_update(phase, pages, discovered))
            except RuntimeError:
                pass

        return _callback

    async def run_check_async(
        self,
        check_id: UUID,
        url: str,
        db: Optional[AsyncSession] = None,
        max_pages: Optional[int] = None,
        update_state: Optional[Callable[[str, Optional[dict]], None]] = None,
    ) -> Dict[str, Any]:
        """Execute the link analysis workflow: discover -> crawl -> check -> analyze -> persist.

        Uses its own DB session if *db* is None (Celery worker path).
        """
        start_time = time.perf_counter()
        canonical_url = _normalize_target_url(url)
        parsed = urlparse(canonical_url)
        domain = normalize_host(parsed.netloc) or ""

        if update_state:
            update_state("PROGRESS", {"phase": "processing", "message": "Starting link analysis..."})

        if db is not None:
            return await self._execute(check_id, domain, db, max_pages, update_state, start_time)

        async with async_session_factory() as session:
            try:
                result = await self._execute(check_id, domain, session, max_pages, update_state, start_time)
                await session.commit()
                return result
            except Exception:
                await session.rollback()
                raise

    async def _execute(
        self,
        check_id: UUID,
        domain: str,
        db: AsyncSession,
        max_pages: Optional[int],
        update_state: Optional[Callable[[str, Optional[dict]], None]],
        start_time: float,
    ) -> Dict[str, Any]:
        # Check if already completed (idempotent re-run protection via acks_late)
        repo = LinkAnalysisRepository(db, redis=self.redis)
        check = await repo.get(check_id)
        if check is None:
            raise ValueError(f"LinkAnalysisCheck with id {check_id} not found")

        if check.status == LinkAnalysisCheckStatus.COMPLETED.value:
            logger.info(f"run_check_async: check {check_id} already completed, skipping")
            return {
                "status": "completed",
                "check_id": str(check_id),
                "domain": domain,
            }

        try:
            # 1. Start crawling
            await repo.mark_processing(
                check_id,
                progress={"phase": "crawling", "message": f"Crawling {domain}..."},
            )
            if update_state:
                update_state("PROGRESS", {"phase": "crawling", "message": f"Crawling {domain}..."})

            progress_cb = self._progress_callback(check_id, db)
            crawler = SiteCrawler(
                canonical_url=check.url,
                domain=domain,
                max_pages=max_pages,
                progress_callback=progress_cb,
            )
            crawl_result: CrawlResult = await crawler.crawl()

            # 2. Link check external + uncrawled internal URLs
            await repo.update_progress(
                check_id,
                LinkAnalysisCheckStatus.PROCESSING,
                progress={"phase": "checking_links", "message": "Checking external and uncrawled links..."},
            )
            if update_state:
                update_state("PROGRESS", {
                    "phase": "checking_links",
                    "message": "Checking external and uncrawled links...",
                    "pages_crawled": len(crawl_result.graph.pages),
                })

            # Collect URLs that need checking:
            # - All external unique target URLs from edges
            # - Internal URLs that were referenced but never fetched
            # - Sitemap-only URLs not crawled
            base_host = crawl_result.graph.base_host
            external_urls: Set[str] = set()
            internal_unfetched: Set[str] = set()

            for page_node in crawl_result.graph.pages.values():
                for edge in page_node.outgoing_edges:
                    if edge.is_internal:
                        if edge.target_url not in crawl_result.graph.pages:
                            internal_unfetched.add(edge.target_url)
                    else:
                        external_urls.add(edge.target_url)

            # Add sitemap-only URLs (normalized)
            for url in crawl_result.sitemap_urls:
                try:
                    from app.shared.utils.url_utils import normalize_url
                    norm = normalize_url(url)
                except Exception:
                    norm = url
                if norm not in crawl_result.graph.pages:
                    internal_unfetched.add(norm)

            # Deduplicate and cap
            unique_to_check: Set[str] = external_urls | internal_unfetched
            if len(external_urls) > settings.LINK_ANALYSIS_MAX_EXTERNAL_CHECKS:
                external_urls = set(list(external_urls)[:settings.LINK_ANALYSIS_MAX_EXTERNAL_CHECKS])
            if len(internal_unfetched) > settings.LINK_ANALYSIS_MAX_SITEMAP_ONLY_CHECKS:
                internal_unfetched = set(list(internal_unfetched)[:settings.LINK_ANALYSIS_MAX_SITEMAP_ONLY_CHECKS])

            unique_to_check = external_urls | internal_unfetched

            checker = LinkChecker()
            checked_results = await checker.check_urls(unique_to_check)

            # Merge checked results into crawl_result.checked_urls
            crawl_result.checked_urls.update(checked_results)

            # 3. Analyze
            all_findings: List[FindingCandidate] = analyze(
                graph=crawl_result.graph,
                checked_urls=crawl_result.checked_urls,
                sitemap_urls=crawl_result.sitemap_urls,
                crawl_truncated=crawl_result.crawl_truncated,
            )

            optimization_findings = analyze_optimization(
                graph=crawl_result.graph,
                crawl_truncated=crawl_result.crawl_truncated,
            )

            all_findings.extend(optimization_findings)

            # Compute overall status (from standard findings only)
            overall_val, severity_val = compute_overall_status(all_findings)
            overall_status = LinkAnalysisOverallStatus(overall_val)
            severity = LinkAnalysisSeverity(severity_val)

            # Build summary
            summary = compute_summary(
                graph=crawl_result.graph,
                checked_urls=crawl_result.checked_urls,
                findings=all_findings,
                sitemap_urls=crawl_result.sitemap_urls,
                crawl_truncated=crawl_result.crawl_truncated,
            )
            summary["blocked_by_robots"] = crawl_result.blocked_by_robots
            page_analysis = summary.pop("pages", [])

            cost_seconds = round(time.perf_counter() - start_time, 3)

            await repo.delete_findings(check_id)
            await repo.replace_pages(check_id, page_analysis)

            finding_rows: List[LinkFinding] = [
                _candidate_to_finding_row(check_id, f) for f in all_findings
            ]
            severity_order = {
                "critical": 0, "high": 1, "medium": 2, "low": 3, "none": 4,
            }
            finding_rows.sort(
                key=lambda f: (
                    severity_order.get(f.severity, 99),
                    f.type,
                    f.target_url,
                )
            )
            await repo.add_findings(finding_rows)

            await repo.mark_completed(
                check_id=check_id,
                summary=summary,
                overall_status=overall_status,
                severity=severity,
                cost_seconds=cost_seconds,
                pages_crawled=len(crawl_result.graph.pages),
                crawl_truncated=crawl_result.crawl_truncated,
            )

            if update_state:
                update_state("PROGRESS", {"phase": "completed", "message": "Link analysis complete"})

            logger.info(
                f"LinkAnalysisService.run_check_async: completed check_id={check_id}, "
                f"pages={len(crawl_result.graph.pages)}, "
                f"findings={len(all_findings)}, "
                f"overall={overall_val}, cost={cost_seconds}s"
            )

            return {
                "status": "completed",
                "check_id": str(check_id),
                "domain": domain,
                "overall_status": overall_val,
                "total_findings": len(all_findings),
                "total_issues": summary["total_issues"],
                "total_opportunities": summary["total_opportunities"],
                "cost_seconds": cost_seconds,
            }

        except Exception as exc:
            logger.error(
                f"LinkAnalysisService._execute failed for check_id={check_id}: {exc}",
                exc_info=True,
            )
            await repo.mark_failed(check_id, str(exc))
            if update_state:
                update_state("FAILURE", {"exc": str(exc)})
            raise
