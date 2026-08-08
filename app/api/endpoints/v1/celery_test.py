from fastapi import APIRouter

from app.core.logger import logger
from app.modules.auth.tasks import send_welcome_email_task

router = APIRouter()


@router.post("/test-celery")
async def run_task():
    logger.info("POST /test-celery - Celery test endpoint called")

    task = send_welcome_email_task.delay("test@example.com")

    return {
        "task_id": task.id,
        "status": "Task submitted",
    }
