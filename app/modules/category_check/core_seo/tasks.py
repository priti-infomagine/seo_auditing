"""
Celery tasks for the Core SEO crawler pipeline.

Architecture:
    run_audit  (coordinator task) — discovers pages → dispatches per-page tasks via chord → finalize
    crawl_page_task (worker task) — full page analysis: crawl → parse → rules → score
    finalize_audit_task (callback) — collects results from all page tasks, computes scores

Same-domain pages are processed in parallel via Celery chord(group(...)) across
multiple Celery workers. The chord callback finalizes once all pages complete.
"""
from __future__ import annotations

import logging
from typing import Any

from app.core.logger import logger

try:
    from app.shared.tasks.celery_app import celery_app
    from app.shared.tasks.db import run_async as _run_async
    from celery import group as celery_group, chord as celery_chord
    CELERY_AVAILABLE = True
except ImportError:
    celery_app = None
    _run_async = None
    celery_group = None
    celery_chord = None
    CELERY_AVAILABLE = False
    logger = logging.getLogger(__name__)

from .pipeline import CoreSEOCrawlerService


def _serialize_rule_results(page_score) -> dict[str, Any]:
    """Serialize a PageScore's rule results into a JSON-safe dict."""
    rule_results_serialized = {}
    for rule_id, rr in page_score.rule_results.items():
        rule_results_serialized[rule_id] = {
            "rule_id": rr.rule_id,
            "name": rr.name,
            "category": rr.category,
            "severity": rr.severity,
            "passed": rr.passed,
            "message": rr.message,
            "recommendation": rr.recommendation,
            "data": rr.data,
            "tags": rr.tags,
            "score_impact": rr.score_impact,
        }
    return rule_results_serialized


def _serialize_page_score(page_score, crawl_result) -> dict[str, Any]:
    """Serialize a PageScore + CrawlResult for cross-worker transport."""
    return {
        "url": page_score.url,
        "score": page_score.score,
        "overall_score": page_score.overall_score,
        "grade": "",
        "on_page_score": page_score.on_page_score,
        "technical_score": page_score.technical_score,
        "passed": page_score.passed,
        "failed": page_score.failed,
        "total_rules": page_score.total_rules,
        "status_code": crawl_result.status_code,
        "success": crawl_result.success,
        "response_time_ms": crawl_result.response_time_ms,
        "rule_results": _serialize_rule_results(page_score),
    }


def _collect_events(audit_id: str) -> list[dict[str, Any]]:
    """Collect and serialize all events emitted during this process."""
    from .events import EventBus
    events = EventBus.get_events_for_audit(audit_id)
    return [
        {
            "event_type": e.event_type,
            "audit_id": e.audit_id,
            "url": e.url,
            "timestamp": e.timestamp,
            "payload": e.payload or e.data,
        }
        for e in events
    ]


# ── Worker Task: crawl_page ───────────────────────────────────────────────────

if CELERY_AVAILABLE:

    @celery_app.task(name="core_seo.crawl_page", bind=True, max_retries=3)
    def crawl_page_task(
        self,
        url: str,
        audit_id: str,
        index: int = 0,
        total: int = 1,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Crawl, parse, run rules, and score a single page.

        Runs on a Celery worker. Emits pipeline events at each stage:
        CRAWL_STARTED → PAGE_CRAWLED → RULES_EVALUATED → SCORE_CALCULATED.

        Each page is an independent unit of work — multiple pages from
        the same domain run in parallel on different workers via Celery group.

        Returns a serialized dict with the page score, crawl result,
        and events emitted during processing (for cross-worker aggregation).
        """
        options = options or {}

        try:
            service = CoreSEOCrawlerService()
            page_score, crawl_result = _run_async(
                service.process_page(url, audit_id, index=index, total=total)
            )
        except Exception as exc:
            self.retry(exc=exc, countdown=60) if self else None
            return {
                "url": url,
                "error": str(exc),
                "status_code": 0,
                "success": False,
                "response_time_ms": 0,
                "score": 0.0,
                "rule_results": {},
                "passed": 0,
                "failed": 0,
                "total_rules": 18,
                "events": [],
            }

        # Collect events emitted during this page's processing
        events = _collect_events(audit_id)

        # Keep only events related to this specific URL
        page_events = [
            e for e in events
            if e.get("url") == url or e.get("event_type") in (
                "crawl_started", "page_crawled", "rules_evaluated",
                "score_calculated", "page_crawl_failed",
            )
        ]

        result = _serialize_page_score(page_score, crawl_result)
        result["events"] = page_events

        # Clear events for this audit to prevent duplicates when finalize runs
        from .events import EventBus
        EventBus._events.pop(audit_id, None)

        return result


def crawl_page_inline(
    url: str,
    audit_id: str,
    index: int = 0,
    total: int = 1,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Non-Celery fallback: run crawl_page_task logic inline."""
    import asyncio
    service = CoreSEOCrawlerService()

    async def _run():
        return await service.process_page(url, audit_id, index=index, total=total)

    page_score, crawl_result = asyncio.run(_run())

    events = _collect_events(audit_id)
    page_events = [
        e for e in events
        if e.get("url") == url or e.get("event_type") in (
            "crawl_started", "page_crawled", "rules_evaluated",
            "score_calculated", "page_crawl_failed",
        )
    ]

    result = _serialize_page_score(page_score, crawl_result)
    result["events"] = page_events

    from .events import EventBus
    EventBus._events.pop(audit_id, None)

    return result


# Re-export crawl_page_task (Celery task or inline fallback)
if not CELERY_AVAILABLE:
    crawl_page_task = crawl_page_inline  # type: ignore[assignment, misc]


# ── Finalize Task (Celery chord callback) ──────────────────────────────────────

if CELERY_AVAILABLE:

    @celery_app.task(name="core_seo.finalize_audit")
    def finalize_audit_task(
        page_results: list[dict[str, Any]],
        audit_id: str,
    ) -> str:
        """Chordin callback: called after all crawl_page_tasks complete.

        Receives the list of serialized page results, restores event state
        from each page, and finalizes the audit.
        """
        service = CoreSEOCrawlerService()

        # Restore events from each page's collected events
        from .events import EventBus
        all_page_events = []
        for pr in page_results:
            if isinstance(pr, dict) and "events" in pr:
                all_page_events.extend(pr["events"])
            elif isinstance(pr, Exception):
                all_page_events.append({
                    "event_type": "page_crawl_failed",
                    "audit_id": audit_id,
                    "url": "",
                    "timestamp": "",
                    "payload": {"error": str(pr)},
                })
        EventBus.add_events_for_audit(audit_id, all_page_events)

        # Finalize the audit
        _run_async(service.finalize_from_results(audit_id, page_results))

        # Write-behind: flush audit state to DB after completion
        try:
            from .storage import WriteBehindStore
            store = WriteBehindStore()
            store.flush()
        except Exception as exc:
            logger.warning("finalize_audit_task: DB flush failed: %s", exc)

        return audit_id


def finalize_audit_inline(
    page_results: list[dict[str, Any]],
    audit_id: str,
) -> str:
    """Non-Celery fallback for finalize_audit_task."""
    import asyncio
    service = CoreSEOCrawlerService()

    # Restore events
    from .events import EventBus
    all_page_events = []
    for pr in page_results:
        if isinstance(pr, dict) and "events" in pr:
            all_page_events.extend(pr["events"])
    EventBus.add_events_for_audit(audit_id, all_page_events)

    async def _finalize():
        await service.finalize_from_results(audit_id, page_results)

    asyncio.run(_finalize())
    return audit_id


if not CELERY_AVAILABLE:
    finalize_audit_task = finalize_audit_inline  # type: ignore[assignment, misc]


# ── Coordinator Task: run_audit ─────────────────────────────────────────────────

if CELERY_AVAILABLE:

    @celery_app.task(name="core_seo.run_audit", bind=True, max_retries=3)
    def run_audit(
        self,
        start_url: str,
        max_pages: int = 10,
        max_depth: int = 3,
        audit_id: str | None = None,
        options: dict[str, Any] | None = None,
    ) -> str:
        """Coordinate a full Core SEO audit via Celery.

        Steps:
        1. Discover pages (sitemap + BFS) — emits CRAWL_STARTED + PAGE_DISCOVERED
        2. Dispatch crawl_page_task per URL via Celery chord(group) — parallel
        3. chord callback (finalize_audit_task) collects results and finalizes

        Same-domain pages run in parallel across Celery workers.
        Returns immediately with the audit_id (finalization happens async via chord).
        """
        options = options or {}
        service = CoreSEOCrawlerService()

        # Phase 1: Discover pages (emits CRAWL_STARTED + PAGE_DISCOVERED)
        try:
            audit_id, urls = _run_async(
                service.discover_pages_async(
                    start_url=start_url,
                    max_pages=max_pages,
                    max_depth=max_depth,
                    audit_id=audit_id,
                )
            )
        except Exception as exc:
            logger.error("Audit discovery failed: %s", exc)
            self.retry(exc=exc, countdown=60) if self else None
            raise

        if not urls:
            # No pages to process — finalize empty audit
            _run_async(service.finalize_from_results(audit_id, []))
            return audit_id

        # Phase 2: Dispatch per-page tasks via Celery chord (parallel group + callback)
        page_group = celery_group(
            crawl_page_task.s(url, audit_id, i, len(urls), {})
            for i, url in enumerate(urls)
        )

        # chord: group runs in parallel, then callback receives all results
        # Returns immediately — finalization happens async via chord callback
        celery_chord(page_group)(finalize_audit_task.s(audit_id))


def run_audit_inline(
    start_url: str,
    max_pages: int = 10,
    max_depth: int = 3,
    audit_id: str | None = None,
    options: dict[str, Any] | None = None,
) -> str:
    """Non-Celery fallback for run_audit — runs inline with asyncio."""
    import asyncio
    service = CoreSEOCrawlerService()

    async def _run_audit():
        nonlocal audit_id
        audit_id, urls = await service.discover_pages_async(
            start_url=start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            audit_id=audit_id,
        )

        if urls:
            page_tasks = [
                service.process_page(url, audit_id, index=i, total=len(urls))
                for i, url in enumerate(urls)
            ]
            results = await asyncio.gather(*page_tasks, return_exceptions=True)

            serialized = []
            page_events = []
            for i, r in enumerate(results):
                if isinstance(r, Exception):
                    serialized.append({"url": urls[i], "error": str(r)})
                    page_events.append({
                        "event_type": "page_crawl_failed",
                        "audit_id": audit_id,
                        "url": urls[i],
                        "timestamp": "",
                        "payload": {"error": str(r)},
                    })
                else:
                    ps, cr = r
                    serialized.append(_serialize_page_score(ps, cr))
                    # Collect events for this page
                    from .events import EventBus
                    events = EventBus.get_events_for_audit(audit_id)
                    page_events.extend([
                        {
                            "event_type": e.event_type,
                            "audit_id": e.audit_id,
                            "url": e.url,
                            "timestamp": e.timestamp,
                            "payload": e.payload or e.data,
                        }
                        for e in events if e.url == urls[i] or e.event_type in (
                            "crawl_started", "page_crawled", "rules_evaluated",
                            "score_calculated", "page_crawl_failed",
                        )
                    ])

            # Store events for finalize
            from .events import EventBus
            # Merge page events into the audit's stored events
            from .events import PipelineEvent
            for pe in page_events:
                EventBus._events[audit_id].append(PipelineEvent(
                    event_type=pe["event_type"],
                    audit_id=pe["audit_id"],
                    url=pe.get("url", ""),
                    timestamp=pe.get("timestamp", ""),
                    data=pe.get("payload", {}),
                ))

            await service.finalize_from_results(audit_id, serialized)
        else:
            await service.finalize_from_results(audit_id, [])

    asyncio.run(_run_audit())
    return audit_id


if not CELERY_AVAILABLE:
    run_audit = run_audit_inline  # type: ignore[assignment, misc]


__all__ = [
    "crawl_page_inline", "crawl_page_task",
    "finalize_audit_task", "finalize_audit_inline",
    "run_audit", "run_audit_inline",
]
