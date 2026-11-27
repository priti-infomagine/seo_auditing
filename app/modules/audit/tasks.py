"""
Audit Celery tasks.

Tasks:
  - audit.parse_crawl: DB-backed parse phase
  - audit.evaluate_rules: Rule evaluation phase
  - audit.score_project: Scoring + output file generation
  - audit.run_analysis_pipeline: Full pipeline (parse → evaluate → score)

All tasks use audit_id (== audit_id) as the single tracking key.
All tasks are fault-tolerant: per-page/rule failures are caught and
recorded; only system-level failures cause the task to fail.
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from uuid import UUID

from app.core.datetime_utils import utc_now
from app.core.logger import logger
from app.modules.audit.events import AuditEventBus, AuditEventType
from app.modules.audit.services.db_parser_service import DBParserService
from app.modules.audit.services.rule_evaluator_service import RuleEvaluatorService
from app.modules.audit.services.analysis_scorer_service import AnalysisScorerService
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="audit.parse_crawl",
    queue="audit",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    acks_late=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def parse_crawl(audit_id: str, force: bool = False) -> dict:
    """
    Celery task: parse all crawled pages for a crawl job and persist
    ParsedPageFact rows to PostgreSQL.

    Args:
        audit_id: The audit ID (== audit_id).

    Returns:
        Summary dict from DBParserService.parse_crawl()
    """
    logger.info(
        f"audit.parse_crawl: task started for audit_id={audit_id}"
    )

    async def _run():
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            service = DBParserService(db)
            result = await service.parse_crawl(UUID(audit_id), force=force)
            await db.commit()
            return result

    try:
        result = run_async(_run())
        logger.info(
            f"audit.parse_crawl: task finished for audit_id={audit_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.parse_crawl: task failed for audit_id={audit_id}: {exc}",
            exc_info=True,
        )
        raise


@celery_app.task(
    name="audit.evaluate_rules",
    queue="audit",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    acks_late=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def evaluate_rules(audit_id: str, force: bool = False) -> dict:
    """
    Celery task: run all 60+ SEO rules against each parsed page and
    persist RuleEvaluationResult rows to PostgreSQL.

    Args:
        audit_id: The audit ID (== audit_id).

    Returns:
        Summary dict from RuleEvaluatorService.evaluate_crawl()
    """
    logger.info(
        f"audit.evaluate_rules: task started for audit_id={audit_id}"
    )

    async def _run():
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            service = RuleEvaluatorService(db)
            result = await service.evaluate_crawl(UUID(audit_id), force=force)
            await db.commit()
            return result

    try:
        result = run_async(_run())
        logger.info(
            f"audit.evaluate_rules: task finished for audit_id={audit_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.evaluate_rules: task failed for audit_id={audit_id}: {exc}",
            exc_info=True,
        )
        raise


@celery_app.task(
    name="audit.score_project",
    queue="audit",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    acks_late=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def score_project(audit_id: str, force: bool = False) -> dict:
    """
    Celery task: score the rule evaluation results, persist SeoAnalysisRun,
    and write the output JSON file.

    Args:
        audit_id: The audit ID (== audit_id).

    Returns:
        Dict from AnalysisScorerService.score_project()
    """
    logger.info(
        f"audit.score_project: task started for audit_id={audit_id}"
    )

    async def _run():
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            service = AnalysisScorerService(db)
            result = await service.score_project(UUID(audit_id), force=force)
            await db.commit()
            return result

    try:
        result = run_async(_run())
        logger.info(
            f"audit.score_project: task finished for audit_id={audit_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.score_project: task failed for audit_id={audit_id}: {exc}",
            exc_info=True,
        )
        raise


async def _invalidate_previous_audit_result(audit_id: str):
    """Remove cached and on-disk results before recomputing this audit."""
    from app.core.redis import get_redis

    redis_client = get_redis()
    if redis_client:
        try:
            await redis_client.delete(
                f"audit:result:{audit_id}:full",
                f"audit:result:{audit_id}:compact",
            )
        except Exception as exc:
            logger.warning(
                "Could not invalidate cached results for audit_id=%s: %s",
                audit_id,
                exc,
            )

    output_dir = Path("app/output")
    if output_dir.exists():
        for result_path in output_dir.glob(f"*_{audit_id}.json"):
            try:
                result_path.unlink()
            except OSError as exc:
                logger.error(
                    "Could not remove stale result file %s: %s",
                    result_path,
                    exc,
                )
    return redis_client


@celery_app.task(
    name="audit.run_analysis_pipeline",
    queue="audit",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    max_retries=3,
    acks_late=True,
    time_limit=3600,
    soft_time_limit=3300,
)
def run_analysis_pipeline(self, audit_id: str, force: bool = False) -> dict:
    """
    Celery task: run the full analysis pipeline sequentially.

    1. Link Check: broken link detection
    2. Site Signals: collect TLS, redirect, security headers (once per audit)
    3. Parse: parse all crawl pages → parsed_page_facts
    4. Evaluate: run all rules → rule_evaluation_results
    5. Score: aggregate, score, persist, write output file → seo_analysis_runs

    Link and site-signal checks are best-effort. Parse, evaluation, and
    scoring failures stop the dependent stages and produce a failed status.

    Args:
        audit_id: The audit ID (== audit_id).

    Returns:
        Dict with results from all stages.
    """
    logger.info(
        f"audit.run_analysis_pipeline: task started for audit_id={audit_id}"
    )
    task_id = self.request.id

    def _report_progress(stage: str) -> None:
        if task_id:
            self.update_state(
                task_id=task_id,
                state="PROGRESS",
                meta={"stage": stage, "audit_id": audit_id},
            )

    async def _run():
        from app.core.database import async_session_factory

        # Initialize AuditEventBus for real-time event streaming
        event_bus = AuditEventBus()
        event_bus.set_audit_state(audit_id, status="analyzing", pipeline_started_at=utc_now().isoformat())
        event_bus.emit(AuditEventType.PIPELINE_STARTED, audit_id=audit_id)

        results: dict = {
            "audit_id": audit_id,
            "status": "running",
        }
        stage_status = {
            "parse": "pending",
            "evaluate": "pending",
            "score": "pending",
        }
        current_stage = "link_check"
        pipeline_error = None
        failed_stage = None
        redis_client = await _invalidate_previous_audit_result(audit_id)

        async def _cache_pipeline_status(status: str, error: str | None = None) -> None:
            if not redis_client:
                return
            status_payload = {
                "audit_id": str(audit_id),
                "status": status,
                "current_stage": current_stage,
                "parse_status": stage_status["parse"],
                "evaluate_status": stage_status["evaluate"],
                "score_status": stage_status["score"],
                "pages_parsed": (results.get("parse") or {}).get("pages_parsed", 0),
                "overall_score": (results.get("score") or {}).get("summary", {}).get("score"),
                "grade": (results.get("score") or {}).get("summary", {}).get("grade"),
                "error": error,
            }
            try:
                await redis_client.set(
                    f"audit:status:{audit_id}",
                    json.dumps(status_payload, default=str),
                    ex=86400,
                )
            except Exception as exc:
                logger.warning(
                    "Could not cache pipeline status for audit_id=%s: %s",
                    audit_id,
                    exc,
                )

        await _cache_pipeline_status("running")

        # Stage 0: Broken link check (runs after crawl, before parse)
        _report_progress("link_check")
        logger.info(
            f"audit.run_analysis_pipeline: STAGE link_check starting "
            f"audit_id={audit_id}"
        )
        try:
            async with async_session_factory() as db:
                from app.modules.crawler.services.broken_link_checker import BrokenLinkChecker
                checker = BrokenLinkChecker(db)
                results["link_check"] = (await checker.check_links(UUID(audit_id))).to_dict()
                await db.commit()
            logger.info(
                f"audit.run_analysis_pipeline: STAGE link_check finished "
                f"audit_id={audit_id}"
            )
        except Exception as exc:
            logger.error(
                f"audit.run_analysis_pipeline: link_check stage failed: {exc}",
                exc_info=True,
            )
            results["link_check"] = {"error": str(exc)}

        # Stage 1: Collect site signals (NEW - for security checks)
        _report_progress("site_signals")
        event_bus.emit(AuditEventType.SITE_SIGNALS_STARTED, audit_id=audit_id)
        logger.info(
            f"audit.run_analysis_pipeline: STAGE site_signals starting "
            f"audit_id={audit_id}"
        )
        try:
            from app.modules.audit.services.security.collector import collect_site_signals
            from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
            async with async_session_factory() as db:
                job_repo = CrawlJobRepository(db)
                job = await job_repo.get_by_id(UUID(audit_id))
                if job:
                    site_signals = await collect_site_signals(audit_id, job.url)
                    results["site_signals"] = {"collected": True, "hostname": site_signals.hostname}
                else:
                    results["site_signals"] = {"error": "CrawlJob not found"}
            logger.info(
                f"audit.run_analysis_pipeline: STAGE site_signals finished "
                f"audit_id={audit_id}"
            )
            event_bus.emit(AuditEventType.SITE_SIGNALS_COMPLETE, audit_id=audit_id, data={"hostname": site_signals.hostname if job else "unknown"})
        except Exception as exc:
            logger.error(
                f"audit.run_analysis_pipeline: site_signals stage failed: {exc}",
                exc_info=True,
            )
            results["site_signals"] = {"error": str(exc)}

        # Stage 2: Parse
        current_stage = "parse"
        await _cache_pipeline_status("running")
        _report_progress("parse")
        event_bus.emit(AuditEventType.PARSE_STARTED, audit_id=audit_id)
        logger.info(
            f"audit.run_analysis_pipeline: STAGE parse starting "
            f"audit_id={audit_id}, force={force}"
        )
        try:
            async with async_session_factory() as db:
                parser = DBParserService(db)
                results["parse"] = await parser.parse_crawl(
                    UUID(audit_id), force=force
                )
                await db.commit()
                stage_status["parse"] = "completed"
            logger.info(
                f"audit.run_analysis_pipeline: STAGE parse finished "
                f"audit_id={audit_id}"
            )
            event_bus.emit(AuditEventType.PARSE_COMPLETE, audit_id=audit_id, data=results.get("parse", {}))
        except Exception as exc:
            logger.error(
                f"audit.run_analysis_pipeline: parse stage failed: {exc}",
                exc_info=True,
            )
            results["parse"] = {"error": str(exc)}
            stage_status["parse"] = "failed"
            pipeline_error = f"parse stage failed: {exc}"
            failed_stage = "parse"

        # Stage 3: Evaluate
        current_stage = "evaluate"
        await _cache_pipeline_status("running")
        _report_progress("evaluate")
        event_bus.emit(AuditEventType.EVALUATE_STARTED, audit_id=audit_id)
        logger.info(
            f"audit.run_analysis_pipeline: STAGE evaluate starting "
            f"audit_id={audit_id}, force={force}"
        )
        if pipeline_error:
            results["evaluate"] = {"error": "Skipped because the parse stage failed"}
            stage_status["evaluate"] = "failed"
        else:
            try:
                async with async_session_factory() as db:
                    evaluator = RuleEvaluatorService(db)
                    evaluate_result = await evaluator.evaluate_crawl(
                        UUID(audit_id), force=force
                    )
                    results["evaluate"] = evaluate_result
                    if (
                        evaluate_result.get("pages_evaluated", 0) <= 0
                        or evaluate_result.get("scorable_results", 0) <= 0
                    ):
                        raise RuntimeError(
                            "Rule evaluation produced no persisted scorable results"
                        )
                    await db.commit()
                stage_status["evaluate"] = "completed"
                logger.info(
                    f"audit.run_analysis_pipeline: STAGE evaluate finished "
                    f"audit_id={audit_id}"
                )
                event_bus.emit(
                    AuditEventType.EVALUATE_COMPLETE,
                    audit_id=audit_id,
                    data=results["evaluate"],
                )
            except Exception as exc:
                logger.error(
                    f"audit.run_analysis_pipeline: evaluate stage failed: {exc}",
                    exc_info=True,
                )
                if isinstance(results.get("evaluate"), dict):
                    results["evaluate"]["error"] = str(exc)
                else:
                    results["evaluate"] = {"error": str(exc)}
                stage_status["evaluate"] = "failed"
                pipeline_error = f"evaluate stage failed: {exc}"
                failed_stage = "evaluate"
                event_bus.emit(
                    AuditEventType.EVALUATE_COMPLETE,
                    audit_id=audit_id,
                    data={"status": "failed", "error": str(exc)},
                )

        # Stage 4: Score
        current_stage = "score"
        await _cache_pipeline_status("running")
        if pipeline_error:
            results["score"] = {
                "error": f"Skipped because {pipeline_error}"
            }
            stage_status["score"] = "failed"
        else:
            _report_progress("score")
            event_bus.emit(AuditEventType.SCORE_STARTED, audit_id=audit_id)
            logger.info(
                f"audit.run_analysis_pipeline: STAGE score starting "
                f"audit_id={audit_id}, force={force}"
            )
            try:
                async with async_session_factory() as db:
                    scorer = AnalysisScorerService(db)
                    results["score"] = await scorer.score_project(
                        UUID(audit_id), force=force
                    )
                    await db.commit()
                stage_status["score"] = "completed"
                logger.info(
                    f"audit.run_analysis_pipeline: STAGE score finished "
                    f"audit_id={audit_id}"
                )
                event_bus.emit(
                    AuditEventType.SCORE_COMPLETE,
                    audit_id=audit_id,
                    data=results["score"],
                )
            except Exception as exc:
                logger.error(
                    f"audit.run_analysis_pipeline: score stage failed: {exc}",
                    exc_info=True,
                )
                results["score"] = {"error": str(exc)}
                stage_status["score"] = "failed"
                pipeline_error = f"score stage failed: {exc}"
                failed_stage = "score"
                event_bus.emit(
                    AuditEventType.SCORE_COMPLETE,
                    audit_id=audit_id,
                    data={"status": "failed", "error": str(exc)},
                )

        # Store final report in Redis state for WebSocket final snapshot
        score_data = results.get("score")
        succeeded = (
            pipeline_error is None
            and stage_status["parse"] == "completed"
            and stage_status["evaluate"] == "completed"
            and stage_status["score"] == "completed"
            and isinstance(score_data, dict)
            and "error" not in score_data
        )
        results["status"] = "completed" if succeeded else "failed"
        current_stage = "completed" if succeeded else (failed_stage or "failed")
        if succeeded:
            event_bus.set_audit_state(audit_id, status="completed", report=score_data)
        else:
            event_bus.set_audit_state(
                audit_id,
                status="failed",
                error=(pipeline_error or "Audit pipeline did not produce a valid score"),
            )

        # Emit final pipeline completed/failed event
        if succeeded:
            event_bus.emit(AuditEventType.PIPELINE_COMPLETED, audit_id=audit_id, data={"summary": score_data.get("summary", {})})
        else:
            event_bus.emit(
                AuditEventType.PIPELINE_FAILED,
                audit_id=audit_id,
                data={"error": pipeline_error or "Audit pipeline did not produce a valid score"},
            )

        if succeeded and redis_client:
            try:
                await redis_client.set(
                    f"audit:result:{audit_id}:full",
                    json.dumps(score_data, default=str),
                    ex=86400,
                )
            except Exception as redis_exc:
                logger.warning(
                    "Failed to cache audit result in Redis for audit_id=%s: %s",
                    audit_id,
                    redis_exc,
                )
        await _cache_pipeline_status(
            results["status"],
            None if succeeded else (pipeline_error or "Audit pipeline did not produce a valid score"),
        )

        return results

    try:
        result = run_async(_run())
        logger.info(
            f"audit.run_analysis_pipeline: task finished for "
            f"audit_id={audit_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.run_analysis_pipeline: pipeline failed for "
            f"audit_id={audit_id}: {exc}",
            exc_info=True,
        )
        # Emit failed event
        event_bus = AuditEventBus()
        event_bus.set_audit_state(audit_id, status="failed", error=str(exc)[:1024])
        event_bus.emit(AuditEventType.PIPELINE_FAILED, audit_id=audit_id, data={"error": str(exc)[:1024]})
        raise
