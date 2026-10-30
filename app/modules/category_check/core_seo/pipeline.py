"""
CoreSEOCrawlerService — orchestrates discovery → crawl → parse → rules → summarize.

Entry point for a full Core SEO audit. Each page is treated as a task;
pipeline-stage events are emitted via EventBus (Redis-first).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from .config import CoreSEOConfig
from .constants import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES
from .crawler import Crawler
from .events import EventBus
from .models import (
    AuditReport,
    CoreSEOEventType,
    CrawlResult,
    DiscoveredURL,
    NormalizedResult,
    PageScore,
    RuleResult,
    Severity,
    PipelineEvent,
)
from .page_discoverer import PageDiscoverer
from .page_parser import PageParser
from .rules.registry import RuleRegistry, default_registry
from .storage import WriteBehindStore
from .summary import summarize_page

from app.core.logger import logger
from app.modules.separate_checks.sitemap_check.errors import (
    NO_SITEMAP_MESSAGE,
    NoSitemapAvailableError,
)

# ContentCrawlerService is imported lazily in __init__ to avoid circular imports:
# core_seo/__init__.py → content/__init__.py → content/config.py →
# core_seo/__init__.py (already loading).


class CoreSEOCrawlerService:
    """Service that runs a complete Core SEO audit pipeline.

    Architecture: discover pages → crawl each → parse HTML →
    run SEO rules (emitting per-rule events) → summarize → finalize.
    """

    def __init__(
        self,
        config: CoreSEOConfig | None = None,
        crawler: Crawler | None = None,
        parser: PageParser | None = None,
        rule_registry: RuleRegistry | None = None,
        event_bus: EventBus | None = None,
        page_discoverer: PageDiscoverer | None = None,
        content_service: ContentCrawlerService | None = None,
        run_content: bool = True,
    ):
        self.config = config or CoreSEOConfig()
        self.crawler = crawler or Crawler()
        self.parser = parser or PageParser()
        self.rule_registry = rule_registry or default_registry()
        self.event_bus = event_bus or EventBus()
        self.page_discoverer = page_discoverer or PageDiscoverer(
            crawler=self.crawler, config=self.config
        )
        self._write_behind: WriteBehindStore = WriteBehindStore()
        self.run_content = run_content
        if run_content:
            if content_service is None:
                from ..content.pipeline import ContentCrawlerService as _ContentCrawlerService
                content_service = _ContentCrawlerService(crawler=self.crawler, page_discoverer=self.page_discoverer)
        else:
            content_service = None
        self.content_service = content_service

    async def start_audit(
        self,
        start_url: str,
        max_pages: int | None = None,
        max_depth: int | None = None,
        audit_id: str | None = None,
        require_sitemap: bool = False,
        preflight_sitemap_urls: list[str] | None = None,
    ) -> str:
        """Start a full Core SEO audit from a start URL.

        Publishes events::
            AUDIT_STARTED → PAGE_DISCOVERED → (per page) PAGE_QUEUED,
            PAGE_STARTED, FETCH_STARTED, PARSED, 18× RULE_CHECKED,
            PAGE_COMPLETED → AUDIT_COMPLETED

        Returns:
            The audit_id.
        """
        if audit_id is None:
            audit_id = str(uuid.uuid4())

        max_pages = max_pages or self.config.max_pages or DEFAULT_MAX_PAGES
        max_depth = max_depth or self.config.max_depth or DEFAULT_MAX_DEPTH

        self.event_bus.reset_counters(audit_id)
        self.event_bus.set_audit_state(
            audit_id,
            status="running",
            total_pages=max_pages,
            start_url=start_url,
            started_at=datetime.utcnow().isoformat(),
        )
        self._write_behind.mark_dirty(audit_id)

        await self._emit_event(CoreSEOEventType.AUDIT_STARTED, audit_id, {
            "start_url": start_url,
            "max_pages": max_pages,
            "max_depth": max_depth,
        })

        discovered_urls = await self.page_discoverer.discover_pages(
            start_url=start_url,
            max_pages=max_pages,
            max_depth=max_depth,
            preflight_sitemap_urls=preflight_sitemap_urls,
        )

        # Sitemap-required gate: when enabled, the audit must not proceed
        # unless live discovery found at least one sitemap-sourced URL. This is
        # evaluated here (after discovery) so the gate is exercised only by the
        # real crawl path; callers that pass require_sitemap=False (e.g. tests)
        # are unaffected.
        if require_sitemap:
            has_sitemap = any(
                du.source_type == "sitemap" for du in discovered_urls
            )
            if not has_sitemap:
                await self._emit_event(
                    CoreSEOEventType.AUDIT_FAILED, audit_id,
                    {"error": NO_SITEMAP_MESSAGE, "start_url": start_url},
                )
                EventBus.set_audit_state(
                    audit_id, status="failed",
                    start_url=start_url, error=NO_SITEMAP_MESSAGE,
                )
                self._write_behind.mark_dirty(audit_id)
                raise NoSitemapAvailableError()

        for du in discovered_urls:
            await self._emit_event(CoreSEOEventType.PAGE_DISCOVERED, audit_id, {
                "url": du.url,
                "source_type": du.source_type,
                "depth": du.depth,
            })

        tasks = [
            self.process_page(
                du.url, audit_id, index=i, total=len(discovered_urls)
            )
            for i, du in enumerate(discovered_urls)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                await self._emit_event(
                    CoreSEOEventType.PAGE_FAILED, audit_id,
                    {"url": discovered_urls[i].url, "error": str(result), "stage": "processing"},
                )

        await self.finalize_audit(audit_id)
        return audit_id

    async def process_page(
        self,
        url: str,
        audit_id: str,
        index: int = 0,
        total: int = 1,
    ) -> tuple[PageScore, CrawlResult]:
        """Crawl, parse, and evaluate rules for a single page.

        Emits per-step and per-rule events to Redis:
        PAGE_QUEUED → PAGE_STARTED → FETCH_STARTED → PARSED →
        18× RULE_CHECKED → PAGE_COMPLETED

        On fetch error: emits PAGE_FAILED with a ``stage`` field and returns
        an empty PageScore.
        """
        await self._emit_event(CoreSEOEventType.PAGE_QUEUED, audit_id, {
            "url": url,
            "index": index,
            "total": total,
        })
        await self._emit_event(CoreSEOEventType.PAGE_STARTED, audit_id, {
            "url": url,
            "index": index,
            "total": total,
        })

        # ── Fetch ──────────────────────────────────────────────
        await self._emit_event(CoreSEOEventType.FETCH_STARTED, audit_id, {"url": url})
        try:
            crawl_result = await self.crawler.crawl(url)
        except Exception as exc:
            await self._emit_event(CoreSEOEventType.PAGE_FAILED, audit_id, {
                "url": url,
                "error": str(exc),
                "stage": "fetch",
            })
            crawl_result = CrawlResult(
                url=url, error=str(exc), success=False,
            )
            if self.run_content and self.content_service:
                await self.content_service.process_page(
                    url=url, audit_id=audit_id, index=index, total=total,
                    crawl_result=crawl_result,
                )
            return PageScore(url=url), crawl_result

        if not crawl_result.success:
            await self._emit_event(CoreSEOEventType.PAGE_FAILED, audit_id, {
                "url": url,
                "error": crawl_result.error or "Unknown crawl error",
                "stage": "fetch",
            })
            empty = PageScore(url=url)
            self._write_behind.write_result(audit_id, empty, crawl_result)
            if self.run_content and self.content_service:
                await self.content_service.process_page(
                    url=url, audit_id=audit_id, index=index, total=total,
                    crawl_result=crawl_result,
                )
            return empty, crawl_result

        # ── Parse ──────────────────────────────────────────────
        html = crawl_result.html or ""
        parsed = self.parser.parse(html, url)
        rule_data = self.parser.build_rule_data(parsed, crawl_result)
        await self._emit_event(CoreSEOEventType.PARSED, audit_id, {"url": url})

        # ── Rules (iterate individually for per-rule events) ────
        rules = self.rule_registry.get_rules()
        all_results: list[RuleResult] = []

        for i, rule in enumerate(rules, 1):
            try:
                results = rule.evaluate(rule_data)
                if results is None:
                    results = []
                elif not isinstance(results, list):
                    results = [results]
            except Exception:
                result = RuleResult(
                    rule_id=rule.rule_id,
                    name=rule.name,
                    passed=False,
                    severity=Severity.ERROR.value,
                    message=f"Rule evaluation failed: {rule.name}",
                    recommendation="Check rule implementation for data mismatch",
                    details={"error": True},
                )
                results = [result]

            all_results.extend(results)
            result = results[0] if results else RuleResult(
                rule_id=rule.rule_id,
                name=rule.name,
                passed=False,
                severity=Severity.ERROR.value,
                message="No results returned from rule evaluation",
                details={"error": True},
            )

            await self._emit_event(CoreSEOEventType.RULE_CHECKED, audit_id, {
                "url": url,
                "rule_id": result.rule_id,
                "name": result.name,
                "passed": result.passed,
                "severity": result.severity,
                "message": result.message,
                "recommendation": result.recommendation,
                "details": result.details or {},
                "checked": i,
                "of": len(rules),
            })

        # ── Page summary ────────────────────────────────────────
        summary = summarize_page(all_results)
        page_score = PageScore(
            url=url,
            passed=summary.passed,
            failed=summary.failed,
            total=summary.total,
            pass_percentage=summary.pass_percentage,
            rule_results=all_results,
        )

        page_state = {
            "url": url,
            "status": "completed",
            "passed": summary.passed,
            "failed": summary.failed,
            "total": summary.total,
            "pass_percentage": summary.pass_percentage,
            "timestamp": datetime.utcnow().isoformat(),
        }
        EventBus.set_page_state(audit_id, url, page_state)

        await self._emit_event(CoreSEOEventType.PAGE_COMPLETED, audit_id, {
            "url": url,
            "passed": summary.passed,
            "failed": summary.failed,
            "total": summary.total,
            "pass_percentage": summary.pass_percentage,
        })

        self._write_behind.write_result(audit_id, page_score, crawl_result)

        if self.run_content and self.content_service:
            await self.content_service.process_page(
                url=url, audit_id=audit_id, index=index, total=total,
                crawl_result=crawl_result, parsed_page=parsed,
            )

        return page_score, crawl_result

    async def discover_pages_async(
        self,
        start_url: str,
        max_pages: int | None = None,
        max_depth: int | None = None,
        audit_id: str | None = None,
        require_sitemap: bool = False,
    ) -> tuple[str, list[str]]:
        """Discover pages and emit events, but don't process them.

        Returns (audit_id, list_of_urls_to_process).
        """
        if audit_id is None:
            audit_id = str(uuid.uuid4())

        max_pages = max_pages or self.config.max_pages or DEFAULT_MAX_PAGES
        max_depth = max_depth or self.config.max_depth or DEFAULT_MAX_DEPTH

        self.event_bus.reset_counters(audit_id)
        self.event_bus.set_audit_state(
            audit_id,
            status="running",
            total_pages=max_pages,
            start_url=start_url,
            started_at=datetime.utcnow().isoformat(),
        )
        self._write_behind.mark_dirty(audit_id)

        await self._emit_event(CoreSEOEventType.AUDIT_STARTED, audit_id, {
            "start_url": start_url,
            "max_pages": max_pages,
            "max_depth": max_depth,
        })

        discovered_urls = await self.page_discoverer.discover_pages(
            start_url=start_url,
            max_pages=max_pages,
            max_depth=max_depth,
        )

        for du in discovered_urls:
            await self._emit_event(CoreSEOEventType.PAGE_DISCOVERED, audit_id, {
                "url": du.url,
                "source_type": du.source_type,
                "depth": du.depth,
            })

        return audit_id, [du.url for du in discovered_urls]

    async def finalize_audit(
        self,
        audit_id: str,
    ) -> AuditReport:
        """Finalize audit: read counters + page states from Redis, compute totals,
        set completed state, emit AUDIT_COMPLETED, flush to DB.

        Does NOT re-add events or re-increment counters. Reads everything
        from Redis (the single source of truth).
        """
        counters = EventBus.get_counters(audit_id)
        page_states = EventBus.get_all_page_states(audit_id)
        state = EventBus.get_audit_state(audit_id)

        if self.run_content and self.content_service:
            from ..content.events import ContentEventBus
            # Let the content service finalize its own audit state (sets
            # status="completed", computes report, emits AUDIT_COMPLETED)
            await self.content_service.finalize_audit(audit_id)
            content_counters = ContentEventBus.get_counters(audit_id)
        else:
            content_counters = {}

        pages_done = counters.get("pages_crawled", 0)
        pages_failed = counters.get("pages_failed", 0)
        pages_discovered = counters.get("pages_discovered", 0)
        rules_passed = counters.get("rules_passed", 0)
        rules_failed = counters.get("rules_failed", 0)
        rules_total = rules_passed + rules_failed
        pass_percentage = round(
            rules_passed / rules_total * 100, 1
        ) if rules_total else 0.0

        content_pages_done = content_counters.get("pages_crawled", 0)
        content_pages_failed = content_counters.get("pages_failed", 0)
        content_rules_passed = content_counters.get("rules_passed", 0)
        content_rules_failed = content_counters.get("rules_failed", 0)
        content_rules_total = content_rules_passed + content_rules_failed
        content_pass_percentage = round(
            content_rules_passed / content_rules_total * 100, 1
        ) if content_rules_total else 0.0

        summary: dict[str, Any] = {
            "pages_total": pages_discovered,
            "pages_done": pages_done,
            "pages_failed": pages_failed,
            "rules_passed": rules_passed,
            "rules_failed": rules_failed,
            "pass_percentage": pass_percentage,
        }

        if self.run_content and self.content_service:
            summary["content_summary"] = {
                "pages_done": content_pages_done,
                "pages_failed": content_pages_failed,
                "rules_passed": content_rules_passed,
                "rules_failed": content_rules_failed,
                "pass_percentage": content_pass_percentage,
            }
            summary.update({
                "content_pages_done": content_pages_done,
                "content_pages_failed": content_pages_failed,
                "content_rules_passed": content_rules_passed,
                "content_rules_failed": content_rules_failed,
                "content_pass_percentage": content_pass_percentage,
            })

        start_url = state.get("start_url", "")
        started_at = state.get("started_at") or datetime.utcnow().isoformat()

        report = AuditReport(
            audit_id=audit_id,
            status="completed",
            start_url=start_url,
            total_pages=pages_discovered,
            crawled_pages=pages_done,
            pages_done=pages_done,
            pages_failed=pages_failed,
            started_at=started_at,
            completed_at=datetime.utcnow().isoformat(),
            summary=summary,
        )

        await self._emit_event(
            CoreSEOEventType.AUDIT_COMPLETED, audit_id,
            {"summary": summary},
        )

        EventBus.set_audit_state(
            audit_id,
            status="completed",
            pages_done=pages_done,
        )

        report_dict = {
            "audit_id": audit_id,
            "status": "completed",
            "start_url": start_url,
            "total_pages": pages_discovered,
            "crawled_pages": pages_done,
            "pages_done": pages_done,
            "pages_failed": pages_failed,
            "rules_passed": rules_passed,
            "rules_failed": rules_failed,
            "pass_percentage": pass_percentage,
            "summary": summary,
            "started_at": started_at,
            "completed_at": datetime.utcnow().isoformat(),
            "pages": [
                {k: v for k, v in page_state.items()}
                for page_state in page_states.values()
            ],
        }
        if self.run_content and self.content_service:
            from ..content.events import ContentEventBus
            content_audit_state = ContentEventBus.get_audit_state(audit_id)
            content_report_json = content_audit_state.get("report")
            content_report_dict = None
            if content_report_json:
                try:
                    content_report_dict = json.loads(content_report_json) if isinstance(content_report_json, str) else content_report_json
                except (json.JSONDecodeError, TypeError):
                    pass
            report_dict["content"] = {
                "summary": {
                    "pages_total": content_pages_done + content_pages_failed,
                    "pages_done": content_pages_done,
                    "pages_failed": content_pages_failed,
                    "rules_passed": content_rules_passed,
                    "rules_failed": content_rules_failed,
                    "pass_percentage": content_pass_percentage,
                },
                "pages": content_report_dict.get("pages", []) if content_report_dict else [],
            }
        EventBus.set_audit_state(audit_id, report=json.dumps(report_dict, default=str))

        self._write_behind.mark_dirty(audit_id)
        self._write_behind.flush()

        return report

    def get_audit_status(self, audit_id: str) -> dict[str, Any]:
        """Return the status dict for a given audit_id from Redis."""
        counters = EventBus.get_counters(audit_id)
        state = EventBus.get_audit_state(audit_id)

        if state.get("status"):
            rules_passed = counters.get("rules_passed", 0)
            rules_failed = counters.get("rules_failed", 0)
            rules_total = rules_passed + rules_failed
            pass_percentage = round(
                rules_passed / rules_total * 100, 1
            ) if rules_total else 0.0

            result = {
                "audit_id": audit_id,
                "status": state.get("status", "unknown"),
                "start_url": state.get("start_url"),
                "error": state.get("error"),
                "total_pages": counters.get("pages_discovered", 0),
                "pages_done": counters.get("pages_crawled", 0),
                "pages_failed": counters.get("pages_failed", 0),
                "rules_passed": rules_passed,
                "rules_failed": rules_failed,
                "pass_percentage": pass_percentage,
            }

            if self.run_content and self.content_service:
                from ..content.events import ContentEventBus
                content_counters = ContentEventBus.get_counters(audit_id)
                content_pass = round(
                    content_counters.get("rules_passed", 0) /
                    (content_counters.get("rules_passed", 0) + content_counters.get("rules_failed", 0)) * 100, 1
                ) if (content_counters.get("rules_passed", 0) + content_counters.get("rules_failed", 0)) else 0.0
                result.update({
                    "content_pages_done": content_counters.get("pages_crawled", 0),
                    "content_pages_failed": content_counters.get("pages_failed", 0),
                    "content_rules_passed": content_counters.get("rules_passed", 0),
                    "content_rules_failed": content_counters.get("rules_failed", 0),
                    "content_pass_percentage": content_pass,
                })

            return result

        if counters["pages_discovered"] > 0 or counters["pages_crawled"] > 0:
            result = {
                "audit_id": audit_id,
                "status": "running",
                "start_url": None,
                "total_pages": counters.get("pages_discovered", 0),
                "pages_done": counters.get("pages_crawled", 0),
                "pages_failed": counters.get("pages_failed", 0),
            }
            if self.run_content and self.content_service:
                from ..content.events import ContentEventBus
                content_counters = ContentEventBus.get_counters(audit_id)
                result.update({
                    "content_pages_done": content_counters.get("pages_crawled", 0),
                    "content_pages_failed": content_counters.get("pages_failed", 0),
                    "content_rules_passed": content_counters.get("rules_passed", 0),
                    "content_rules_failed": content_counters.get("rules_failed", 0),
                })
            return result

        return {"audit_id": audit_id, "status": "unknown"}

    def get_report(self, audit_id: str) -> NormalizedResult | None:
        """Retrieve and build a normalized audit report from Redis state.

        Falls back to the database (AuditCheck.report_json) when Redis
        data has expired (audit finished > 1 hour ago).
        """
        state = EventBus.get_audit_state(audit_id)

        if state.get("status") == "completed":
            report_json = state.get("report")
            if report_json:
                try:
                    report_dict = json.loads(report_json) if isinstance(report_json, str) else report_json
                    return self._build_normalized_from_dict(audit_id, report_dict)
                except (json.JSONDecodeError, TypeError):
                    pass

            # Build from Redis state + page states + events
            counters = EventBus.get_counters(audit_id)
            page_states = EventBus.get_all_page_states(audit_id)
            events = EventBus.get_events_for_audit(audit_id)
            return self._build_normalized_from_redis(audit_id, counters, page_states, events)

        if state.get("status") in ("running", "pending"):
            return None

        # Redis expired — try DB fallback
        return self._build_normalized_from_db(audit_id)

    def _build_normalized_from_dict(
        self, audit_id: str, report_dict: dict[str, Any]
    ) -> NormalizedResult:
        """Build NormalizedResult from a serialized report dict."""
        summary = report_dict.get("summary", {})
        pages_raw = report_dict.get("pages", [])
        pages = []
        for p in pages_raw:
            if isinstance(p, dict):
                pages.append({
                    "url": p.get("url", ""),
                    "status": p.get("status", "completed"),
                    "passed": p.get("passed", 0),
                    "failed": p.get("failed", 0),
                    "total": p.get("total", 0),
                    "pass_percentage": p.get("pass_percentage", 0.0),
                    "results": p.get("rule_results", []),
                })

        # Include content page results from the content sub-report
        content_pages = []
        content_report = report_dict.get("content", {})
        for p in content_report.get("pages", []):
            if isinstance(p, dict):
                content_pages.append({
                    "url": p.get("url", ""),
                    "status": p.get("status", "completed"),
                    "passed": p.get("passed", 0),
                    "failed": p.get("failed", 0),
                    "total": p.get("total", 0),
                    "pass_percentage": p.get("pass_percentage", 0.0),
                    "results": p.get("rule_results", []),
                })

        started_at = report_dict.get("started_at", "")
        completed_at = report_dict.get("completed_at")

        result = NormalizedResult(
            audit_id=audit_id,
            status="completed",
            summary=summary,
            pages=pages,
            page_url="",
            normalized_url="",
            pass_percentage=summary.get("pass_percentage", 0.0),
            timestamp=completed_at or started_at or "",
        )
        result.content_pages = content_pages  # type: ignore[attr-defined]
        return result

    def _build_normalized_from_redis(
        self,
        audit_id: str,
        counters: dict[str, int],
        page_states: dict[str, dict[str, Any]],
        events: list[PipelineEvent],
    ) -> NormalizedResult:
        """Build NormalizedResult directly from Redis data."""
        rules_passed = counters.get("rules_passed", 0)
        rules_failed = counters.get("rules_failed", 0)
        rules_total = rules_passed + rules_failed
        pass_percentage = round(
            rules_passed / rules_total * 100, 1
        ) if rules_total else 0.0

        summary = {
            "pages_total": counters.get("pages_discovered", 0),
            "pages_done": counters.get("pages_crawled", 0),
            "pages_failed": counters.get("pages_failed", 0),
            "rules_passed": rules_passed,
            "rules_failed": rules_failed,
            "pass_percentage": pass_percentage,
        }

        pages = []
        for url, ps in page_states.items():
            pages.append({
                "url": url,
                "status": ps.get("status", "completed"),
                "passed": ps.get("passed", 0),
                "failed": ps.get("failed", 0),
                "total": ps.get("total", 0),
                "pass_percentage": ps.get("pass_percentage", 0.0),
                "results": ps.get("rule_results", []),
            })

        event_list = [
            {
                "event_type": e.event_type,
                "audit_id": e.audit_id,
                "url": e.url,
                "timestamp": e.timestamp,
                "payload": e.payload or e.data,
                "category": "core_seo",
            }
            for e in events
        ]

        # Include content events and page states from the content Redis stream
        content_pages = []
        if self.run_content and self.content_service:
            from ..content.events import ContentEventBus
            content_page_states = ContentEventBus.get_all_page_states(audit_id)
            content_events = ContentEventBus.get_events_for_audit(audit_id)
            for url, ps in content_page_states.items():
                content_pages.append({
                    "url": url,
                    "status": ps.get("status", "completed"),
                    "passed": ps.get("passed", 0),
                    "failed": ps.get("failed", 0),
                    "total": ps.get("total", 0),
                    "pass_percentage": ps.get("pass_percentage", 0.0),
                    "results": ps.get("rule_results", []),
                })
            for e in content_events:
                event_list.append({
                    "event_type": e.event_type,
                    "audit_id": e.audit_id,
                    "url": e.url,
                    "timestamp": e.timestamp,
                    "payload": e.payload or e.data,
                    "category": "content",
                })
            # Sort all events by timestamp
            event_list.sort(key=lambda ev: ev["timestamp"])

        result = NormalizedResult(
            audit_id=audit_id,
            status="completed",
            summary=summary,
            pages=pages,
            page_url="",
            normalized_url="",
            pass_percentage=pass_percentage,
            events=event_list,
        )
        result.content_pages = content_pages
        return result

    def _build_normalized_from_db(self, audit_id: str) -> NormalizedResult | None:
        """Build NormalizedResult from the DB when Redis expired."""
        from app.core.database import async_session_factory
        from .db_models.audit_db import AuditCheck

        try:
            from app.shared.tasks.db import run_async

            async def _load():
                async with async_session_factory() as session:
                    record = await session.get(AuditCheck, audit_id)
                    if record is None:
                        return None
                    report = record.get_report()
                    if report is None:
                        return None
                    return self._build_normalized_from_dict(audit_id, report)

            return run_async(_load())
        except Exception as exc:
            logger.debug("get_report DB fallback failed: %s", exc)
            return None

    async def finalize_from_results(
        self,
        audit_id: str,
        serialized_results: list[dict[str, Any]],
    ) -> str:
        """Finalize audit from serialized Celery task results.

        In the Redis-first design, events are already in Redis from each
        page's process_page call. This method simply reads Redis and finalizes.
        """
        await self.finalize_audit(audit_id)
        return audit_id

    async def _emit_event(
        self,
        event_type: CoreSEOEventType,
        audit_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Emit a pipeline-stage event via the EventBus (Redis write)."""
        event = PipelineEvent(
            event_type=event_type,
            audit_id=audit_id,
            payload=payload,
        )
        await self.event_bus.publish(event)

    def get_rule_registry(self) -> RuleRegistry:
        """Public accessor for the rule registry (for testing/introspection)."""
        return self.rule_registry


__all__ = ["CoreSEOCrawlerService"]
