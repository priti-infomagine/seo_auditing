"""Celery tasks for the redirect check module."""
from __future__ import annotations

from app.core.logger import logger
from app.modules.seprate_checks.redirect_check.service import RedirectCheckService
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="redirect_check.run_domain_check",
    queue="crawler",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=2,
    acks_late=True,
    time_limit=1800,
    soft_time_limit=1700,
    track_started=True,
)
def run_check(self, audit_id: str, domain: str, max_urls: int = 500) -> dict:
    """Celery task: run domain-level redirect chain check with SSE streaming."""
    logger.info("redirect_check.run_check: started audit_id=%s domain=%s max_urls=%d", audit_id, domain, max_urls)
    task_id = self.request.id

    def _report_progress(state: str, meta: dict | None = None):
        if task_id:
            self.update_state(task_id=task_id, state=state, meta=meta)

    async def _run():
        service = RedirectCheckService()
        result = await service.run_check_async(
            audit_id=audit_id,
            domain=domain,
            update_state=_report_progress,
        )
        return result

    try:
        result = run_async(_run())
        logger.info(
            "redirect_check.run_check: completed audit_id=%s status=%s", audit_id, result.get("status")
        )
        return result
    except Exception as exc:
        logger.error("redirect_check.run_check: failed audit_id=%s: %s", audit_id, exc, exc_info=True)
        _report_progress("FAILURE", {"error": str(exc)[:1024]})
        raise
