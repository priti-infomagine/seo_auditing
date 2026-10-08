"""Celery tasks for the redirect check module."""
from __future__ import annotations

from app.core.logger import logger
from app.modules.seprate_checks.redirect_check.service import RedirectCheckService
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="redirect_check.domain_check",
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
def run_check(
    self,
    audit_id: str,
    domain: str,
    max_urls: int = 500,
    max_depth: int = 5,
    max_hops: int = 10,
) -> dict:
    """Celery task: run domain-level redirect chain check with SSE streaming."""
    logger.info(
        "redirect_check.domain_check: started audit_id=%s domain=%s max_urls=%d max_depth=%d max_hops=%d",
        audit_id, domain, max_urls, max_depth, max_hops,
    )
    task_id = self.request.id

    def _report_progress(state: str, meta: dict | None = None):
        if task_id:
            phase = meta.get("phase", "") if meta else ""
            logger.info(
                "redirect_check.domain_check: progress state=%s phase=%s audit_id=%s",
                state, phase, audit_id,
            )
            self.update_state(task_id=task_id, state=state, meta=meta)

    async def _run():
        service = RedirectCheckService()
        result = await service.run_check_async(
            audit_id=audit_id,
            domain=domain,
            max_urls=max_urls,
            update_state=_report_progress,
        )
        return result

    try:
        result = run_async(_run())
        logger.info(
            "redirect_check.domain_check: COMPLETED audit_id=%s status=%s total_checked=%s total_findings=%s cost=%.3fs",
            audit_id,
            result.get("status"),
            result.get("total_checked"),
            result.get("total_findings"),
            result.get("cost_seconds", 0),
        )
        print(
            f"[redirect-check] Done: {result.get('total_checked')} URLs checked, "
            f"{result.get('total_findings')} findings",
            flush=True,
        )
        return result
    except Exception:
        logger.error(
            "redirect_check.domain_check: FAILED audit_id=%s",
            audit_id, exc_info=True,
        )
        print(f"[redirect-check] FAILED for {audit_id}", flush=True)
        raise
