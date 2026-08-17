from fastapi import APIRouter, HTTPException, status

from app.core.logger import logger
from app.modules.auth.tasks import send_welcome_email_task

router = APIRouter()


@router.post("/test-celery")
async def run_task():
    """Celery test endpoint."""
    logger.info("POST /test-celery - Celery test endpoint called")
    try:
        task = send_welcome_email_task.delay("test@example.com")
        return {
            "task_id": task.id,
            "status": "Task submitted",
        }
    except Exception as exc:
        logger.error(f"Celery test task failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to submit test task",
        )
