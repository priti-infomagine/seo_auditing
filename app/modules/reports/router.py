"""
Reports API Router — handles POST /api/v1/reports/{audit_id}/send.
"""
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.reports.tasks import send_audit_report_email_task

router = APIRouter()


class SendReportRequest(BaseModel):
    """Request schema for sending report email."""

    to_email: Optional[EmailStr] = Field(
        None,
        description="Recipient email address. Defaults to REPORT_DEFAULT_RECIPIENT_EMAIL if omitted.",
        examples=["report@yopmail.com"],
    )


class SendReportResponse(BaseModel):
    """Response schema for report email dispatch."""

    audit_id: str
    queued_for: str
    status: str


@router.post(
    "/{audit_id}/send",
    response_model=SendReportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Send PDF audit report via email",
    description=(
        "Enqueues a Celery task to build the PDF report for audit_id and send it "
        "as an email attachment to to_email (or default recipient)."
    ),
)
async def send_audit_report(
    audit_id: UUID,
    body: Optional[SendReportRequest] = None,
    db: AsyncSession = Depends(get_db),
) -> SendReportResponse:
    """
    Queue PDF report generation and email delivery for an audit.

    Args:
        audit_id: The audit ID (== crawl_id).
        body: Request containing optional recipient email.
        db: Database session.

    Returns:
        SendReportResponse with audit_id, queued_for, status.
    """
    logger.info(f"POST /reports/{audit_id}/send")

    job_repo = CrawlJobRepository(db)
    job = await job_repo.get_by_id(audit_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit job {audit_id} not found",
        )

    to_email = (
        str(body.to_email)
        if body and body.to_email
        else settings.REPORT_DEFAULT_RECIPIENT_EMAIL
    )

    send_audit_report_email_task.delay(str(audit_id), to_email)

    logger.info(
        f"POST /reports/{audit_id}/send: queued send_audit_report_email_task for {to_email}"
    )

    return SendReportResponse(
        audit_id=str(audit_id),
        queued_for=to_email,
        status="queued",
    )
