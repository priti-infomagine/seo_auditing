"""
Audit Celery tasks.

Tasks:
  - audit.parse_crawl: DB-backed parse phase
  - audit.evaluate_rules: Rule evaluation phase
  - audit.score_project: Scoring + output file generation
  - audit.run_analysis_pipeline: Full pipeline (parse → evaluate → score)

All tasks use project_id as the tracking key alongside crawl_id.
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
def parse_crawl(project_id: str, crawl_id: str) -> dict:
    """
    Celery task: parse all crawled pages for a crawl job and persist
    ParsedPageFact rows to PostgreSQL.

    Args:
        project_id: The project tracking key.
        crawl_id: The crawl job ID.

    Returns:
        Summary dict from DBParserService.parse_crawl()
    """
    logger.info(
        f"audit.parse_crawl: task started for project_id={project_id}, "
        f"crawl_id={crawl_id}"
    )

    async def _run():
   
        print("=" * 70)
        print("CELERY RUNTIME")
        print("PID:", os.getpid())
        print("Platform:", sys.platform)
        print(
            "Policy:",
            type(asyncio.get_event_loop_policy()).__name__,
        )

        try:
            loop = asyncio.get_running_loop()
            print("Running loop:", type(loop).__name__)
        except RuntimeError:
            print("Running loop: NONE")

        print("=" * 70)

        
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            service = DBParserService(db)
            result = await service.parse_crawl(UUID(project_id), UUID(crawl_id))
            await db.commit()
            return result

    try:
        result = run_async(_run())
        logger.info(
            f"audit.parse_crawl: task finished for project_id={project_id}, "
            f"crawl_id={crawl_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.parse_crawl: task failed for project_id={project_id}, "
            f"crawl_id={crawl_id}: {exc}",
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
def evaluate_rules(project_id: str, crawl_id: str) -> dict:
    """
    Celery task: run all 60+ SEO rules against each parsed page and
    persist RuleEvaluationResult rows to PostgreSQL.

    Args:
        project_id: The project tracking key.
        crawl_id: The crawl job ID.

    Returns:
        Summary dict from RuleEvaluatorService.evaluate_crawl()
    """
    logger.info(
        f"audit.evaluate_rules: task started for project_id={project_id}, "
        f"crawl_id={crawl_id}"
    )

    async def _run():
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            service = RuleEvaluatorService(db)
            result = await service.evaluate_crawl(UUID(project_id), UUID(crawl_id))
            await db.commit()
            return result

    try:
        result = run_async(_run())
        logger.info(
            f"audit.evaluate_rules: task finished for project_id={project_id}, "
            f"crawl_id={crawl_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.evaluate_rules: task failed for project_id={project_id}, "
            f"crawl_id={crawl_id}: {exc}",
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
def score_project(project_id: str, crawl_id: str) -> dict:
    """
    Celery task: score the rule evaluation results, persist SeoAnalysisRun,
    and write the output JSON file.

    Args:
        project_id: The project tracking key.
        crawl_id: The crawl job ID.

    Returns:
        Dict from AnalysisScorerService.score_project()
    """
    logger.info(
        f"audit.score_project: task started for project_id={project_id}, "
        f"crawl_id={crawl_id}"
    )

    async def _run():
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            service = AnalysisScorerService(db)
            result = await service.score_project(UUID(project_id), UUID(crawl_id))
            await db.commit()
            return result

    try:
        result = run_async(_run())
        logger.info(
            f"audit.score_project: task finished for project_id={project_id}, "
            f"crawl_id={crawl_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.score_project: task failed for project_id={project_id}, "
            f"crawl_id={crawl_id}: {exc}",
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
def run_analysis_pipeline(self, project_id: str, crawl_id: str) -> dict:
    """
    Celery task: run the full analysis pipeline sequentially.

    1. Parse: parse all crawl pages → parsed_page_facts
    2. Evaluate: run all rules → rule_evaluation_results
    3. Score: aggregate, score, persist, write output file → seo_analysis_runs

    Each stage is fault-tolerant — errors in one stage don't prevent
    the next from running.

    Args:
        project_id: The project tracking key.
        crawl_id: The crawl job ID.

    Returns:
        Dict with results from all three stages.
    """
    logger.info(
        f"audit.run_analysis_pipeline: task started for project_id={project_id}, "
        f"crawl_id={crawl_id}"
    )

    async def _run():
        from app.core.database import async_session_factory

        results: dict = {
            "project_id": project_id,
            "crawl_id": crawl_id,
        }

        # Stage 1: Parse
        self.update_state(
            state="PROGRESS",
            meta={"stage": "parse", "project_id": project_id},
        )
        logger.info(
            f"audit.run_analysis_pipeline: STAGE parse starting "
            f"project_id={project_id}, crawl_id={crawl_id}"
        )
        try:
            async with async_session_factory() as db:
                parser = DBParserService(db)
                results["parse"] = await parser.parse_crawl(
                    UUID(project_id), UUID(crawl_id)
                )
                await db.commit()
            logger.info(
                f"audit.run_analysis_pipeline: STAGE parse finished "
                f"project_id={project_id}, crawl_id={crawl_id}"
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
            meta={"stage": "evaluate", "project_id": project_id},
        )
        logger.info(
            f"audit.run_analysis_pipeline: STAGE evaluate starting "
            f"project_id={project_id}, crawl_id={crawl_id}"
        )
        try:
            async with async_session_factory() as db:
                evaluator = RuleEvaluatorService(db)
                results["evaluate"] = await evaluator.evaluate_crawl(
                    UUID(project_id), UUID(crawl_id)
                )
                await db.commit()
            logger.info(
                f"audit.run_analysis_pipeline: STAGE evaluate finished "
                f"project_id={project_id}, crawl_id={crawl_id}"
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
            meta={"stage": "score", "project_id": project_id},
        )
        logger.info(
            f"audit.run_analysis_pipeline: STAGE score starting "
            f"project_id={project_id}, crawl_id={crawl_id}"
        )
        try:
            async with async_session_factory() as db:
                scorer = AnalysisScorerService(db)
                results["score"] = await scorer.score_project(
                    UUID(project_id), UUID(crawl_id)
                )
                await db.commit()
            logger.info(
                f"audit.run_analysis_pipeline: STAGE score finished "
                f"project_id={project_id}, crawl_id={crawl_id}"
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
            f"project_id={project_id}, crawl_id={crawl_id}"
        )
        return result
    except Exception as exc:
        logger.error(
            f"audit.run_analysis_pipeline: pipeline failed for "
            f"project_id={project_id}, crawl_id={crawl_id}: {exc}",
            exc_info=True,
        )
        raise
