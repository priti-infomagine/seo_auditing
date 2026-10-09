import asyncio
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException
from starlette import status

from app.core.logger import logger
from app.shared.tasks.celery_app import celery_app

from .schema import (
    RedirectCheckPollResponse,
    RedirectCheckQueuedResponse,
    RedirectCheckRequest,
    RedirectResponse,
)

router = APIRouter()


@router.post(
    "/check",
    response_model=RedirectCheckQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def check_redirects(body: RedirectCheckRequest) -> RedirectCheckQueuedResponse:
    check_id = str(uuid4())

    def enqueue():
        celery_app.backend.store_result(check_id, {"status": "queued"}, "QUEUED")
        return celery_app.send_task(
            "redirect_check.run_check",
            args=[check_id, body.model_dump(mode="json")],
            task_id=check_id,
            queue="crawler",
        )

    try:
        task = await asyncio.to_thread(enqueue)
        return RedirectCheckQueuedResponse(
            check_id=UUID(check_id),
            task_id=task.id,
            status="queued",
            status_url=f"/api/v1/redirect-check/check/{check_id}",
        )
    except Exception as exc:
        await asyncio.to_thread(celery_app.backend.forget, check_id)
        logger.error("Failed to enqueue redirect check %s: %s", check_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to queue redirect check.",
        ) from exc


@router.get("/check/{check_id}", response_model=RedirectCheckPollResponse)
async def poll_redirect_check(check_id: str) -> RedirectCheckPollResponse:
    try:
        parsed_check_id = UUID(check_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid check ID format (must be a valid UUID)",
        ) from exc

    def read_task_state():
        result = celery_app.AsyncResult(str(parsed_check_id))
        return result.state, result.result

    task_state, task_result = await asyncio.to_thread(read_task_state)
    base = {"check_id": parsed_check_id, "task_id": str(parsed_check_id)}

    if task_state == "PENDING":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Redirect check not found or its result has expired.",
        )
    if task_state in {"QUEUED", "RECEIVED"}:
        return RedirectCheckPollResponse(**base, status="queued")
    if task_state in {"STARTED", "PROGRESS"}:
        return RedirectCheckPollResponse(**base, status="running")
    if task_state == "RETRY":
        return RedirectCheckPollResponse(**base, status="retrying")
    if task_state == "REVOKED":
        return RedirectCheckPollResponse(
            **base, status="revoked", error="Redirect check was cancelled."
        )
    if task_state == "FAILURE":
        logger.error(
            "Redirect check %s failed in Celery (%s)",
            parsed_check_id,
            type(task_result).__name__,
        )
        return RedirectCheckPollResponse(
            **base, status="failed", error="Redirect check failed."
        )
    if task_state == "SUCCESS":
        return RedirectCheckPollResponse(
            **base,
            status="completed",
            result=RedirectResponse.model_validate(task_result),
        )
    return RedirectCheckPollResponse(**base, status="running")
