"""
Audit Celery tasks.

Tasks:
  - audit.parse_crawl: DB-backed parse phase
  - audit.evaluate_rules: Rule evaluation phase
  - audit.score_project: Scoring + output file generation
  - audit.run_analysis_pipeline: Full pipeline (parse → evaluate → score)

All tasks use audit_id (== crawl_id) as the single tracking key.
All tasks are fault-tolerant: per-page/rule failures are caught and
recorded; only system-level failures cause the task to fail.
"""
import asyncio
import os
import sys
from uuid import UUID

from app.core.logger import logger
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
        audit_id: The audit ID (== crawl_id).

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
        audit_id: The audit ID (== crawl_id).

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
        audit_id: The audit ID (== crawl_id).

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

    1. Parse: parse all crawl pages → parsed_page_facts
    2. Evaluate: run all rules → rule_evaluation_results
    3. Score: aggregate, score, persist, write output file → seo_analysis_runs

    Each stage is fault-tolerant — errors in one stage don't prevent
    the next from running.

    Args:
        audit_id: The audit ID (== crawl_id).

    Returns:
        Dict with results from all three stages.
    """
    logger.info(
        f"audit.run_analysis_pipeline: task started for audit_id={audit_id}"
    )

    async def _run():
        from app.core.database import async_session_factory

        results: dict = {
            "audit_id": audit_id,
        }

        # Stage 1: Parse
        self.update_state(
            state="PROGRESS",
            meta={"stage": "parse", "audit_id": audit_id},
        )
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
            logger.info(
                f"audit.run_analysis_pipeline: STAGE parse finished "
                f"audit_id={audit_id}"
            )
        except Exception as exc:
            logger.error(
                f"audit.run_analysis_pipeline: parse stage failed: {exc}",
                exc_info=True,
            )
            results["parse"] = {"error": str(exc)}

        # Stage 2: Evaluate
        self.update_state(
            state="PROGRESS",
            meta={"stage": "evaluate", "audit_id": audit_id},
        )
        logger.info(
            f"audit.run_analysis_pipeline: STAGE evaluate starting "
            f"audit_id={audit_id}, force={force}"
        )
        try:
            async with async_session_factory() as db:
                evaluator = RuleEvaluatorService(db)
                results["evaluate"] = await evaluator.evaluate_crawl(
                    UUID(audit_id), force=force
                )
                await db.commit()
            logger.info(
                f"audit.run_analysis_pipeline: STAGE evaluate finished "
                f"audit_id={audit_id}"
            )
        except Exception as exc:
            logger.error(
                f"audit.run_analysis_pipeline: evaluate stage failed: {exc}",
                exc_info=True,
            )
            results["evaluate"] = {"error": str(exc)}

        # Stage 3: Score
        self.update_state(
            state="PROGRESS",
            meta={"stage": "score", "audit_id": audit_id},
        )
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
            logger.info(
                f"audit.run_analysis_pipeline: STAGE score finished "
                f"audit_id={audit_id}"
            )
        except Exception as exc:
            logger.error(
                f"audit.run_analysis_pipeline: score stage failed: {exc}",
                exc_info=True,
            )
            results["score"] = {"error": str(exc)}

        results["status"] = "completed"
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
        raise
