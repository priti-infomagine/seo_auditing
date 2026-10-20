from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async

from .schema import RedirectCheckRequest
from .service import RedirectCheckerService


@celery_app.task(
    name="redirect_check.run_check",
    queue="crawler",
    bind=True,
    acks_late=True,
    track_started=True,
    time_limit=1800,
    soft_time_limit=1700,
)
def run_check(self, check_id: str, request_data: dict) -> dict:
    logger.info("redirect_check.run_check: started check_id=%s", check_id)
    task_id = self.request.id
    if task_id:
        self.update_state(
            task_id=task_id,
            state="PROGRESS",
            meta={"check_id": check_id, "phase": "checking"},
        )

    async def _run() -> dict:
        request = RedirectCheckRequest.model_validate(request_data)
        result = await RedirectCheckerService().check(request)
        return result.model_dump(mode="json", by_alias=True)

    result = run_async(_run())
    logger.info("redirect_check.run_check: completed check_id=%s", check_id)
    return result
