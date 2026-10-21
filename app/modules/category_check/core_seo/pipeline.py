"""
CoreSEOCrawlerService — orchestrates discovery → crawl → parse → rules → score.

Entry point for a full Core SEO audit. Each page is treated as a task;
pipeline-stage events are emitted via EventBus.
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
    CategoryScore,
    CoreSEOEventType,
    CrawlResult,
    NormalizedResult,
    PageResult,
    PageScore,
    PipelineEvent,
)
from .normalizer import AuditNormalizer
from .page_discoverer import PageDiscoverer
from .page_parser import PageParser
from .rules.registry import RuleRegistry, default_registry
from .scorer import Scorer
from .storage import WriteBehindStore

from app.core.logger import logger


class CoreSEOCrawlerService:
    """Service that runs a complete Core SEO audit pipeline.

    Architecture follows: discover pages → crawl each → parse HTML →
    run SEO rules → aggregate scores → normalize report.

    Each page is processed as a discrete step suitable for Celery
    task distribution, but can also run inline.
    """

    def __init__(
        self,
        config: CoreSEOConfig | None = None,
        crawler: Crawler | None = None,
        parser: PageParser | None = None,
        rule_registry: RuleRegistry | None = None,
        scorer: Scorer | None = None,
        event_bus: EventBus | None = None,
        page_discoverer: PageDiscoverer | None = None,
    ):
        self.config = config or CoreSEOConfig()
        self.crawler = crawler or Crawler()
        self.parser = parser or PageParser()
        self.rule_registry = rule_registry or default_registry()
        self.scorer = scorer or Scorer()
        self.event_bus = event_bus or EventBus()
        self.page_discoverer = page_discoverer or PageDiscoverer(
            crawler=self.crawler, config=self.config
        )
        self._normalizer = AuditNormalizer()

        self._audit_states: dict[str, dict[str, Any]] = {}
        self._write_behind: WriteBehindStore = WriteBehindStore()

    async def start_audit(
        self,
        start_url: str,
        max_pages: int | None = None,
        max_depth: int | None = None,
        audit_id: str | None = None,
    ) -> str:
        """Start a full Core SEO audit from a start URL.

        Publishes events::
            CRAWL_STARTED → PAGE_DISCOVERED → PAGE_CRAWLED →
            RULES_EVALUATED → SCORE_CALCULATED → AUDIT_COMPLETED

        Returns:
            The audit_id.
        """
        if audit_id is None:
            audit_id = str(uuid.uuid4())

        max_pages = max_pages or self.config.max_pages or DEFAULT_MAX_PAGES
        max_depth = max_depth or self.config.max_depth or DEFAULT_MAX_DEPTH

        # Persist audit state in-memory AND Redis (cross-process visible by web API)
        self._audit_states[audit_id] = {
            "status": "running",
            "total_pages": max_pages,
            "crawled_pages": 0,
            "start_time": datetime.utcnow(),
            "start_url": start_url,
        }
        self.event_bus.reset_counters(audit_id)
        self.event_bus.set_audit_state(audit_id, status="running", total_pages=max_pages, crawled_pages=0, start_url=start_url)
        self._write_behind.mark_dirty(audit_id)

        await self._emit_event(CoreSEOEventType.CRAWL_STARTED, audit_id, {
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

        page_scores: list[PageScore] = []
        crawl_results: list[CrawlResult] = []
        page_results: list[PageResult] = []

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
                    CoreSEOEventType.PAGE_CRAWL_FAILED, audit_id,
                    {"url": discovered_urls[i].url, "error": str(result)},
                )
                continue
            page_score, crawl_result = result
            page_scores.append(page_score)
            crawl_results.append(crawl_result)
            page_results.append(PageResult(
                url=page_score.url,
                normalized_url=page_score.url,
                status_code=crawl_result.status_code,
                response_time_ms=crawl_result.response_time_ms,
                success=crawl_result.success,
                error=crawl_result.error,
                score=page_score.score,
                page_score=page_score,
                rule_count=len(page_score.rule_results),
                rules_passed=page_score.passed,
                rules_failed=page_score.failed,
            ))

        category_scores = self.scorer.score_pages(page_scores)

        await self._emit_event(
            CoreSEOEventType.SCORE_CALCULATED, audit_id,
            {"overall_score": sum(p.score for p in page_scores) / len(page_scores) if page_scores else 0.0},
        )

        await self.finalize_audit(
            audit_id, page_scores, category_scores, crawl_results
        )
        return audit_id

    async def process_page(
        self,
        url: str,
        audit_id: str,
        index: int = 0,
        total: int = 1,
    ) -> tuple[PageScore, CrawlResult]:
        """Crawl, parse, and evaluate rules for a single page.

        This method is designed to be distributable as a Celery task:
        the logic is self-contained and can be invoked with just (url, audit_id).
        """
        await self._emit_event(CoreSEOEventType.CRAWL_STARTED, audit_id, {
            "url": url,
            "index": index,
            "total": total,
        })

        try:
            crawl_result = await self.crawler.crawl(url)
        except Exception as exc:
            await self._emit_event(
                CoreSEOEventType.PAGE_CRAWL_FAILED, audit_id,
                {"url": url, "error": str(exc)},
            )
            raise

        await self._emit_event(CoreSEOEventType.PAGE_CRAWLED, audit_id, {
            "url": url,
            "status_code": crawl_result.status_code,
        })

        html = crawl_result.html or ""
        parsed = self.parser.parse(html, url)
        rule_data = self.parser.build_rule_data(parsed)

        rule_results = self.rule_registry.run_all(rule_data)

        await self._emit_event(CoreSEOEventType.RULES_EVALUATED, audit_id, {
            "url": url,
            "rule_count": len(rule_results),
        })

        page_score = self.scorer.score_page(url, rule_results)

        await self._emit_event(
            CoreSEOEventType.SCORE_CALCULATED, audit_id,
            {"url": url, "score": page_score.score},
        )

        self._write_behind.write_result(audit_id, page_score, crawl_result)

        return page_score, crawl_result

    async def discover_pages_async(
        self,
        start_url: str,
        max_pages: int | None = None,
        max_depth: int | None = None,
        audit_id: str | None = None,
    ) -> tuple[str, list[str]]:
        """Discover pages and emit events, but don't process them.

        Returns (audit_id, list_of_urls_to_process).
        Used by ``run_audit`` to dispatch per-page Celery tasks.
        """
        if audit_id is None:
            audit_id = str(uuid.uuid4())

        max_pages = max_pages or self.config.max_pages or DEFAULT_MAX_PAGES
        max_depth = max_depth or self.config.max_depth or DEFAULT_MAX_DEPTH

        # Persist audit state in-memory AND Redis (cross-process visible by web API)
        self._audit_states[audit_id] = {
            "status": "running",
            "total_pages": max_pages,
            "crawled_pages": 0,
            "start_time": datetime.utcnow(),
            "start_url": start_url,
        }
        self.event_bus.reset_counters(audit_id)
        self.event_bus.set_audit_state(audit_id, status="running", total_pages=max_pages, crawled_pages=0, start_url=start_url)
        self._write_behind.mark_dirty(audit_id)

        await self._emit_event(CoreSEOEventType.CRAWL_STARTED, audit_id, {
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

    def deserialize_page_score(self, data: dict[str, Any]) -> PageScore:
        """Reconstruct a PageScore from serialized Celery task result."""
        from .models import RuleResult

        rule_results = {}
        for k, v in (data.get("rule_results") or {}).items():
            rule_results[k] = RuleResult(
                rule_id=v["rule_id"],
                name=v["name"],
                category=v["category"],
                severity=v.get("severity", "warning"),
                passed=v["passed"],
                message=v.get("message", ""),
                recommendation=v.get("recommendation"),
                data=v.get("data"),
                tags=v.get("tags", []),
                score_impact=v.get("score_impact", 0.0),
            )

        return PageScore(
            url=data["url"],
            score=data["score"],
            overall_score=data.get("overall_score", data["score"]),
            grade=data.get("grade", ""),
            category_scores={},
            total_rules=data.get("total_rules", len(rule_results)),
            passed=data.get("passed", 0),
            failed=data.get("failed", 0),
            on_page_score=data.get("on_page_score", 100.0),
            technical_score=data.get("technical_score", 100.0),
            rule_results=rule_results,
        )

    async def finalize_from_results(
        self,
        audit_id: str,
        serialized_results: list[dict[str, Any]],
    ) -> str:
        """Finalize audit from serialized Celery task results.

        Args:
            audit_id: The audit identifier.
            serialized_results: List of dicts returned by crawl_page_task.

        Returns:
            The audit_id.
        """
        page_scores: list[PageScore] = []
        crawl_results: list[CrawlResult] = []

        for result in serialized_results:
            if result is None:
                continue
            if result.get("error"):
                await self._emit_event(
                    CoreSEOEventType.PAGE_CRAWL_FAILED, audit_id,
                    {"url": result.get("url", ""), "error": result["error"]},
                )
                continue

            page_score = self.deserialize_page_score(result)
            page_scores.append(page_score)
            crawl_results.append(CrawlResult(
                url=result["url"],
                html="",
                status_code=result["status_code"],
                success=result["success"],
                response_time_ms=result["response_time_ms"],
            ))

        category_scores = self.scorer.score_pages(page_scores)

        await self._emit_event(
            CoreSEOEventType.SCORE_CALCULATED, audit_id,
            {"overall_score": round(sum(p.score for p in page_scores) / len(page_scores), 2) if page_scores else 0.0},
        )

        await self.finalize_audit(audit_id, page_scores, category_scores, crawl_results)
        return audit_id

    async def finalize_audit(
        self,
        audit_id: str,
        page_scores: list[PageScore],
        category_scores: list[CategoryScore],
        crawl_results: list[CrawlResult],
    ) -> AuditReport:
        """Finalize audit: compute overall, build report, emit completion."""
        overall_score = self.scorer.calculator.calculate_overall_score(page_scores)
        grade = self.scorer.calculator.determine_grade(overall_score)

        events = self.event_bus.get_events_for_audit(audit_id)

        # Retrieve start_url from state (in-memory or Redis)
        state = self._audit_states.get(audit_id, {})
        if not state:
            state = self.event_bus.get_audit_state(audit_id)
        start_url = state.get("start_url", "")

        report = AuditReport(
            audit_id=audit_id,
            status="completed",
            start_url=start_url,
            total_pages=len(page_scores),
            crawled_pages=len(page_scores),
            total_time_seconds=0.0,
            overall_score=overall_score,
            grade=grade,
            categories=category_scores,
            pages=page_scores,
            events=events,
        )

        await self._emit_event(
            CoreSEOEventType.AUDIT_COMPLETED, audit_id,
            {"overall_score": overall_score, "grade": grade, "total_pages": len(page_scores)},
        )

        # Persist completion state to Redis (cross-process visible by web API)
        self.event_bus.set_audit_state(
            audit_id,
            status="completed",
            crawled_pages=len(page_scores),
            overall_score=overall_score,
            grade=grade,
        )
        # Store serialized report for later retrieval (cross-process)
        try:
            from dataclasses import asdict
            report_dict = asdict(report)
            report_json = json.dumps(report_dict, default=str)
            self.event_bus.set_audit_state(audit_id, report=report_json)
        except (TypeError, ValueError):
            pass

        self._write_behind.mark_dirty(audit_id)
        self._write_behind.flush()

        state = self._audit_states.get(audit_id, {})
        state["status"] = "completed"
        state["end_time"] = datetime.utcnow()
        state["overall_score"] = overall_score
        state["grade"] = grade
        state["report"] = report
        state["crawled_pages"] = len(page_scores)
        self._audit_states[audit_id] = state

        return report

    def get_audit_status(self, audit_id: str) -> dict[str, Any]:
        """Return the status dict for a given audit_id.

        Reads from EventBus which falls back to Redis for cross-process
        visibility (when Celery worker set state but this is the web API process).
        """
        # Try in-memory first
        state = self._audit_states.get(audit_id, {})
        if not state:
            # Fall back to Redis-backed EventBus state
            state = self.event_bus.get_audit_state(audit_id)
            counters = self.event_bus.get_counters(audit_id)
            if state:
                state.setdefault("total_pages", counters.get("pages_discovered", 0))
                state.setdefault("crawled_pages", counters.get("pages_crawled", 0))

        if not state:
            # No state found anywhere — check if counters exist (partial progress)
            counters = self.event_bus.get_counters(audit_id)
            if counters["pages_discovered"] > 0 or counters["pages_crawled"] > 0:
                return {
                    "audit_id": audit_id,
                    "status": "running",
                    "total_pages": counters.get("pages_discovered", 0),
                    "crawled_pages": counters.get("pages_crawled", 0),
                    "start_url": None,
                    "overall_score": None,
                    "grade": None,
                }
            return {"audit_id": audit_id, "status": "unknown"}

        return {
            "audit_id": audit_id,
            "status": state.get("status", "unknown"),
            "total_pages": state.get("total_pages", 0),
            "crawled_pages": state.get("crawled_pages", 0),
            "start_url": state.get("start_url"),
            "overall_score": state.get("overall_score"),
            "grade": state.get("grade"),
        }

    def _build_report_from_dict(self, data: dict[str, Any]) -> AuditReport | None:
        """Attempt to reconstruct an AuditReport from a serialized dict (Redis)."""
        try:
            from .models import RuleResult

            # Reconstruct pages (PageScore with nested RuleResult)
            pages: list[PageScore] = []
            for p in data.get("pages", []):
                if isinstance(p, dict):
                    rule_results_raw = p.get("rule_results", {})
                    rule_results: dict[str, RuleResult] = {}
                    for rule_key, rule_val in rule_results_raw.items():
                        if isinstance(rule_val, dict):
                            rule_results[rule_key] = RuleResult(**rule_val)
                        else:
                            rule_results[rule_key] = rule_val
                    pages.append(PageScore(
                        url=p.get("url", ""),
                        score=p.get("score", 0.0),
                        overall_score=p.get("overall_score", 0.0),
                        grade=p.get("grade", "F"),
                        category_scores=p.get("category_scores", {}),
                        total_rules=p.get("total_rules", 0),
                        passed=p.get("passed", 0),
                        failed=p.get("failed", 0),
                        on_page_score=p.get("on_page_score", 100.0),
                        technical_score=p.get("technical_score", 100.0),
                        rule_results=rule_results,
                    ))
                else:
                    pages.append(p)

            # Reconstruct categories
            categories_raw = data.get("categories", {})
            if isinstance(categories_raw, list):
                categories = [CategoryScore(**c) if isinstance(c, dict) else c for c in categories_raw]
            elif isinstance(categories_raw, dict):
                categories = {k: CategoryScore(**v) if isinstance(v, dict) else v for k, v in categories_raw.items()}
            else:
                categories = categories_raw

            # Reconstruct events (PipelineEvent)
            events_raw = data.get("events", [])
            if isinstance(events_raw, list):
                events: list[PipelineEvent] = []
                for e in events_raw:
                    if isinstance(e, dict):
                        # PipelineEvent has __post_init__ that syncs data/payload
                        et = e.get("event_type", "")
                        if hasattr(CoreSEOEventType, et.upper().replace("_", "")):
                            try:
                                et = CoreSEOEventType(et).value
                            except ValueError:
                                pass
                        events.append(PipelineEvent(
                            event_type=et,
                            audit_id=e.get("audit_id", ""),
                            url=e.get("url", ""),
                            timestamp=e.get("timestamp", ""),
                            data=e.get("data", {}),
                        ))
                    else:
                        events.append(e)

            return AuditReport(
                audit_id=data.get("audit_id", ""),
                domain=data.get("domain", ""),
                status=data.get("status", "completed"),
                start_url=data.get("start_url", ""),
                total_pages=data.get("total_pages", 0),
                crawled_pages=data.get("crawled_pages", 0),
                pages_crawled=data.get("pages_crawled", 0),
                pages_failed=data.get("pages_failed", 0),
                pages_skipped=data.get("pages_skipped", 0),
                categories=categories,
                overall_score=data.get("overall_score", 0.0),
                grade=data.get("grade", "F"),
                started_at=data.get("started_at", ""),
                completed_at=data.get("completed_at"),
                total_time_seconds=data.get("total_time_seconds", 0.0),
                page_results=data.get("page_results", []),
                pages=pages,
                events=events,
                errors=data.get("errors", []),
            )
        except (TypeError, KeyError, ValueError) as exc:
            logger.debug("Failed to reconstruct AuditReport: %s", exc)
            return None

    def get_report(self, audit_id: str) -> NormalizedResult | None:
        """Retrieve and normalize a completed audit report.

        Reads from in-memory state first; falls back to Redis-backed EventBus
        state for cross-process visibility (when Celery worker stored the
        report but this is the web API process).
        """
        report_state = self._audit_states.get(audit_id, {})
        if not report_state:
            # Fall back to Redis-backed EventBus state
            report_state = self.event_bus.get_audit_state(audit_id)

        if report_state.get("status") != "completed":
            return None

        events = self.event_bus.get_events_for_audit(audit_id)
        report = report_state.get("report")

        if report is not None and isinstance(report, str):
            # Report was stored as JSON string in Redis
            try:
                report_dict = json.loads(report)
                # Reconstruct AuditReport from dict
                report_obj = self._build_report_from_dict(report_dict)
            except (json.JSONDecodeError, TypeError):
                report_obj = None
        elif report is not None and isinstance(report, AuditReport):
            # In-memory AuditReport object
            report_obj = report
        else:
            report_obj = None

        if report_obj is not None:
            return self._normalizer.normalize(report_obj)

        return self._normalizer.normalize_from_state(
            audit_id=audit_id,
            overall_score=report_state.get("overall_score", 0.0),
            grade=report_state.get("grade", "F"),
            events=events,
        )

    async def _emit_event(
        self,
        event_type: CoreSEOEventType,
        audit_id: str,
        payload: dict[str, Any],
    ) -> None:
        """Emit a pipeline-stage event via the EventBus."""
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
