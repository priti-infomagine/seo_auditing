from __future__ import annotations

from uuid import UUID

from app.core.database import async_session_factory
from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async

from .service import RedirectUrlAuditService


@celery_app.task(
    name="redirect_check.run_domain_check",
    queue="crawler",
    bind=True,
    acks_late=True,
    track_started=True,
    time_limit=1800,
    soft_time_limit=1700,
)
def run_redirect_url_audit(
    self,
    audit_id: str,
    domain: str,
    max_urls: int,
    max_depth: int = 5,
    max_hops: int = 10,
) -> dict:
    logger.info(
        "redirect_check.run_domain_check: started audit_id=%s domain=%s max_urls=%d max_depth=%d max_hops=%d",
        audit_id,
        domain,
        max_urls,
        max_depth,
        max_hops,
    )

    def update_task_state(state: str, meta: dict) -> None:
        logger.info(
        "Celery progress update: task_id=%s state=%s meta=%s",
        self.request.id,
        state,
        meta,
        )
        
    if not self.request.id:
        logger.error(
        "Celery task ID is missing! task=%r request=%r",
        self,
        self.request,
    )
        return

    async def run() -> dict:
        async with async_session_factory() as session:
            return await RedirectUrlAuditService(session).run(
                UUID(audit_id),
                domain,
                max_urls,
                max_depth,
                max_hops,
                update_task_state=update_task_state,
            )

    try:
        result = run_async(run())
        logger.info(
            "redirect_check.run_domain_check: finished audit_id=%s status=%s checked=%d",
            audit_id,
            result["status"],
            result["total_checked"],
        )
        return result
    except Exception:
        logger.exception("redirect_check.run_domain_check: failed audit_id=%s", audit_id)
        raise
