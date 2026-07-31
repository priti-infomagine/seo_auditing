from fastapi import APIRouter

from app.workers.tasks import test_task

router = APIRouter()

@router.post("/test-celery")
async def run_task():

    task = test_task.delay()

    return {
        "task_id": task.id,
        "status": "Task submitted"
    }