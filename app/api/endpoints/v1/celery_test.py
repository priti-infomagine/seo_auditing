from fastapi import APIRouter, HTTPException, status

from app.core.#loggger import #loggger
from app.modules.auth.tasks import send_welcome_email_task

router = APIRouter()


@router.post("/test-celery")
async def run_task():
    """Celery test endpoint."""
    #loggger.info("POST /test-celery - Celery test endpoint called")
    try:
        task = send_welcome_email_task.delay("test@example.com")
        return {
            "task_id": task.id,
            "status": "Task submitted",
        }
    except Exception as exc:
        #loggger.error(f"Celery test task failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit test task",
        )
