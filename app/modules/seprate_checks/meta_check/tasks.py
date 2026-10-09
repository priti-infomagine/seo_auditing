from uuid import UUID

from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async

from .service import MetaCheckService


@celery_app.task(
    name="meta.run_check",
    queue="crawler",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=2,
    acks_late=True,
    time_limit=900,
    soft_time_limit=840,
    track_started=True,
)
def run_check(self, check_id: str) -> dict:
    logger.info("meta.run_check: task started for check_id=%s", check_id)
    task_id = self.request.id

    def _report_progress(state, meta=None):
        if task_id:
            self.update_state(task_id=task_id, state=state, meta=meta)

    async def _run():
        return await MetaCheckService().run_check_async(
            UUID(check_id),
            update_state=_report_progress,
        )

    return run_async(_run())