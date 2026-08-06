from fastapi import APIRouter

from app.core.logger import logger
from app.workers.tasks import test_task

router = APIRouter()

@router.post("/test-celery")
async def run_task():
    logger.info("POST /test-celery - Celery test endpoint called")

    task = test_task.delay()

    return {
        "task_id": task.id,
        "status": "Task submitted"
    }