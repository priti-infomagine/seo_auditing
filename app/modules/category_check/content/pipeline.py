"""
ContentCrawlerService — orchestrates content rule evaluation for each page.

Called inline from CoreSEOCrawlerService.process_page() after core SEO
rules complete. Emits events to a separate Redis stream
(content:events:{audit_id}) with independent counters, but shares the
same audit_id for combined WebSocket streaming.

Only processes successfully crawled pages — failed pages emit
PAGE_FAILED to the content stream and are skipped.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any

from app.modules.category_check.content.db_models.audit_db import ContentAuditCheck

from .config import CONTENT_RULE_COUNT, ContentConfig
from .events import ContentEventBus
from .data_builder import build_content_rule_data
from .models import (
    AuditReport,
    ContentEventType,
    ContentPipelineEvent,
    CrawlResult,
    DiscoveredURL,
    NormalizedResult,
    PageScore,
    RuleResult,
    Severity,
)
from .page_parser import ContentPageParser
from .rules.registry import ContentRuleRegistry, default_content_registry
from .storage.content_write_behind import ContentWriteBehindStore

from app.core.logger import logger

from app.modules.category_check.core_seo.constants import DEFAULT_MAX_DEPTH, DEFAULT_MAX_PAGES
from app.modules.category_check.core_seo.page_discoverer import PageDiscoverer
from app.modules.category_check.core_seo.crawler import Crawler
from app.modules.category_check.core_seo.summary import summarize_page

_CONTENT_RULE_COUNT = CONTENT_RULE_COUNT
_CONTENT_PAGES_FAILED_KEY = "pages_failed"


class ContentCrawlerService:
    """Service that runs content checks alongside the Core SEO pipeline.

    Architecture: reuses the same Crawler and PageDiscoverer instances as
    CoreSEOCrawlerService, but runs a separate set of 13 content rules
    and emits to a separate Redis namespace.
    """

    def __init__(
        self,
        config: ContentConfig | None = None,
        crawler: Crawler | None = None,
        parser: ContentPageParser | None = None,
        rule_registry: ContentRuleRegistry | None = None,
        event_bus: ContentEventBus | None = None,
        page_discoverer: PageDiscoverer | None = None,
    ):
        self.config = config or ContentConfig()
        self.crawler = crawler or Crawler()
        self.parser = parser or ContentPageParser()
        self.rule_registry = rule_registry or default_content_registry()
        self.event_bus = event_bus or ContentEventBus()
        self.page_discoverer = page_discoverer or PageDiscoverer(
            crawler=self.crawler, config=self.config
        )
        self._write_behind: ContentWriteBehindStore = ContentWriteBehindStore()

    async def process_page(
        self,
        url: str,
        audit_id: str,
        index: int = 0,
        total: int = 1,
        crawl_result: CrawlResult | None = None,
        parsed_page: Any = None,
    ) -> PageScore | None:
        """Run 13 content rules for a single page.

        Called from CoreSEOCrawlerService.process_page() after core rules.
        If crawl_result is None or failed, emits PAGE_FAILED and returns None.

        Emits events to the content: Redis stream:
        PAGE_STARTED → PARSED → 13× RULE_CHECKED → PAGE_COMPLETED
        (or PAGE_FAILED on error).
        """
        print(f"[content] Starting content checks for: {url} (audit={audit_id[:8]})", flush=True)
        if crawl_result is None:
            try:
                crawl_result = await self.crawler.crawl(url)
            except Exception as exc:
                await self._emit_event(ContentEventType.PAGE_FAILED, audit_id, url, {
                    "url": url,
                    "error": str(exc),
                    "stage": "fetch",
                })
                return None

        if not crawl_result.success:
            await self._emit_event(ContentEventType.PAGE_FAILED, audit_id, url, {
                "url": url,
                "error": crawl_result.error or "Crawl failed",
                "stage": "content",
            })
            return None

        await self._emit_event(ContentEventType.PAGE_STARTED, audit_id, {
            "url": url,
            "index": index,
            "total": total,
        })

        html = crawl_result.html or ""
        if parsed_page is None:
            parsed_page = self.parser.parse(html, url)

        rule_data = self.parser.build_content_rule_data(parsed_page, crawl_result)

        await self._emit_event(ContentEventType.PARSED, audit_id, {"url": url})

        rules = self.rule_registry.get_rules()
        all_results: list[RuleResult] = []
        rule_ids_seen: set[str] = set()

        for i, rule in enumerate(rules, 1):
            if rule.rule_id in rule_ids_seen:
                continue
            rule_ids_seen.add(rule.rule_id)
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

            await self._emit_event(ContentEventType.RULE_CHECKED, audit_id, {
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
        ContentEventBus.set_page_state(audit_id, url, page_state)

        await self._emit_event(ContentEventType.PAGE_COMPLETED, audit_id, {
            "url": url,
            "passed": summary.passed,
            "failed": summary.failed,
            "total": summary.total,
            "pass_percentage": summary.pass_percentage,
        })
        print(
            f"[content] Page completed: {url} | "
            f"passed={summary.passed}/{summary.total} | "
            f"failed={summary.failed} | pass%={summary.pass_percentage}%",
            flush=True,
        )

        self._write_behind.write_result(audit_id, page_score, crawl_result)
        return page_score

    async def start_audit(
        self,
        start_url: str,
        max_pages: int | None = None,
        max_depth: int | None = None,
        audit_id: str | None = None,
        require_sitemap: bool = False,
        preflight_sitemap_urls: list[str] | None = None,
    ) -> str:
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

        await self._emit_event(ContentEventType.AUDIT_STARTED, audit_id, {
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

        for du in discovered_urls:
            await self._emit_event(ContentEventType.PAGE_DISCOVERED, audit_id, {
                "url": du.url,
                "source_type": du.source_type,
                "depth": du.depth,
            })

        tasks = [
            self.process_page(du.url, audit_id, index=i, total=len(discovered_urls))
            for i, du in enumerate(discovered_urls)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, result in enumerate(results):
            if isinstance(result, Exception):
                await self._emit_event(ContentEventType.PAGE_FAILED, audit_id, discovered_urls[i].url, {
                    "url": discovered_urls[i].url,
                    "error": str(result),
                    "stage": "processing",
                })

        await self.finalize_audit(audit_id)
        return audit_id

    async def finalize_audit(self, audit_id: str) -> AuditReport:
        counters = ContentEventBus.get_counters(audit_id)
        page_states = ContentEventBus.get_all_page_states(audit_id)
        state = ContentEventBus.get_audit_state(audit_id)

        pages_done = counters.get("pages_crawled", 0)
        pages_failed = counters.get("pages_failed", 0)
        pages_discovered = counters.get("pages_discovered", 0)
        rules_passed = counters.get("rules_passed", 0)
        rules_failed = counters.get("rules_failed", 0)
        rules_total = rules_passed + rules_failed
        pass_percentage = round(
            rules_passed / rules_total * 100, 1
        ) if rules_total else 0.0

        summary: dict[str, Any] = {
            "pages_total": pages_discovered,
            "pages_done": pages_done,
            "pages_failed": pages_failed,
            "rules_passed": rules_passed,
            "rules_failed": rules_failed,
            "pass_percentage": pass_percentage,
        }

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
            ContentEventType.AUDIT_COMPLETED, audit_id,
            {"summary": summary},
        )

        ContentEventBus.set_audit_state(
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
        ContentEventBus.set_audit_state(audit_id, report=json.dumps(report_dict, default=str))

        self._write_behind.mark_dirty(audit_id)
        self._write_behind.flush()

        return report

    def get_audit_status(self, audit_id: str) -> dict[str, Any]:
        counters = ContentEventBus.get_counters(audit_id)
        state = ContentEventBus.get_audit_state(audit_id)

        if state.get("status"):
            rules_passed = counters.get("rules_passed", 0)
            rules_failed = counters.get("rules_failed", 0)
            rules_total = rules_passed + rules_failed
            pass_percentage = round(
                rules_passed / rules_total * 100, 1
            ) if rules_total else 0.0
            return {
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

        if counters["pages_discovered"] > 0 or counters["pages_crawled"] > 0:
            return {
                "audit_id": audit_id,
                "status": "running",
                "start_url": None,
                "total_pages": counters.get("pages_discovered", 0),
                "pages_done": counters.get("pages_crawled", 0),
                "pages_failed": counters.get("pages_failed", 0),
            }

        return {"audit_id": audit_id, "status": "unknown"}

    def get_report(self, audit_id: str) -> NormalizedResult | None:
        state = ContentEventBus.get_audit_state(audit_id)

        if state.get("status") == "completed":
            report_json = state.get("report")
            if report_json:
                try:
                    report_dict = json.loads(report_json) if isinstance(report_json, str) else report_json
                    return self._build_normalized_from_dict(audit_id, report_dict)
                except (json.JSONDecodeError, TypeError):
                    pass

            counters = ContentEventBus.get_counters(audit_id)
            page_states = ContentEventBus.get_all_page_states(audit_id)
            events = ContentEventBus.get_events_for_audit(audit_id)
            return self._build_normalized_from_redis(audit_id, counters, page_states, events)

        if state.get("status") in ("running", "pending"):
            return None

        return self._build_normalized_from_db(audit_id)

    def _build_normalized_from_dict(
        self, audit_id: str, report_dict: dict[str, Any]
    ) -> NormalizedResult:
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

        started_at = report_dict.get("started_at", "")
        completed_at = report_dict.get("completed_at")

        return NormalizedResult(
            audit_id=audit_id,
            status="completed",
            summary=summary,
            pages=pages,
            page_url="",
            normalized_url="",
            pass_percentage=summary.get("pass_percentage", 0.0),
            timestamp=completed_at or started_at or "",
        )

    def _build_normalized_from_redis(
        self,
        audit_id: str,
        counters: dict[str, int],
        page_states: dict[str, dict[str, Any]],
        events: list[ContentPipelineEvent],
    ) -> NormalizedResult:
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
            }
            for e in events
        ]

        return NormalizedResult(
            audit_id=audit_id,
            status="completed",
            summary=summary,
            pages=pages,
            pass_percentage=pass_percentage,
            events=event_list,
        )

    def _build_normalized_from_db(self, audit_id: str) -> NormalizedResult | None:
        from app.core.database import async_session_factory

        try:
            from app.shared.tasks.db import run_async

            async def _load():
                async with async_session_factory() as session:
                    record = await session.get(ContentAuditCheck, audit_id)
                    if record is None:
                        return None
                    report = record.get_report()
                    if report is None:
                        return None
                    return self._build_normalized_from_dict(audit_id, report)

            return run_async(_load())
        except Exception as exc:
            logger.debug("ContentCrawlerService.get_report DB fallback failed: %s", exc)
            return None

    async def finalize_from_results(
        self,
        audit_id: str,
        serialized_results: list[dict[str, Any]],
    ) -> str:
        await self.finalize_audit(audit_id)
        return audit_id

    async def _emit_event(
        self,
        event_type: ContentEventType,
        audit_id: str,
        url_or_payload: str | dict[str, Any],
        payload: dict[str, Any] | None = None,
    ) -> None:
        if isinstance(url_or_payload, str):
            url = url_or_payload
            data = payload or {}
        else:
            url = url_or_payload.get("url", "")
            data = url_or_payload
        event = ContentPipelineEvent(
            event_type=event_type,
            audit_id=audit_id,
            url=url,
            payload=data,
        )
        await self.event_bus.publish(event)

    def get_rule_registry(self) -> ContentRuleRegistry:
        return self.rule_registry


__all__ = ["ContentCrawlerService"]
