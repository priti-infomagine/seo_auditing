"""
Reports API Router.

Endpoints:
- POST /api/v1/reports/{audit_id}/send   → enqueue email delivery (Celery).
- GET  /api/v1/reports/{audit_id}/download → build + store PDF locally and
  stream it back (public, no Celery).
"""
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.logger import logger
from app.modules.crawler.repositories.crawl_job_repository import CrawlJobRepository
from app.modules.reports.services.pdf_generator import render_audit_report_pdf
from app.modules.reports.services.report_data_service import build_audit_report
from app.modules.reports.tasks import send_audit_report_email_task

router = APIRouter()


class SendReportRequest(BaseModel):
    """Request schema for sending report email."""

    email: Optional[EmailStr] = Field(
        None,
        description="Recipient email address. Defaults to REPORT_DEFAULT_RECIPIENT_EMAIL if omitted."
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
        audit_id: The audit ID (== audit_id).
        body: Request containing optional recipient email.
        db: Database session.

    Returns:
        SendReportResponse with audit_id, queued_for, status.
    """
    logger.info(f"POST /reports/{audit_id}/send")

    job_repo = CrawlJobRepository(db)

    # Resolve by audit_id (CrawlJob.id) first; fall back to audit_id so callers
    # can use the public audit_id returned in CrawlResponse.
    job = await job_repo.get_by_id_or_audit_id(audit_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit job {audit_id} not found",
        )

    email = (
        str(body.email)
        if body and body.email
        else settings.REPORT_DEFAULT_RECIPIENT_EMAIL
    )

    send_audit_report_email_task.delay(str(audit_id), email)

    logger.info(
        f"POST /reports/{audit_id}/send: queued send_audit_report_email_task for {email}"
    )

    return SendReportResponse(
        audit_id=str(audit_id),
        queued_for=email,
        status="queued",
    )


@router.get(
    "/{audit_id}/download",
    response_class=FileResponse,
    summary="Download PDF audit report",
    description=(
        "Builds the PDF audit report for audit_id (if not already stored), persists "
        "it locally under output/report/{domain}/ and streams it back as a "
        "downloadable PDF. Public endpoint — no authentication required and no "
        "Celery involvement: everything runs synchronously in the request."
    ),
)
async def download_audit_report(
    audit_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """
    Build + store + download the PDF audit report for an audit, by audit_id.

    Organizes the stored file by the site's domain name (netloc) using the same
    layout the Celery email task uses: ``{REPORT_OUTPUT_DIR}/{domain}/{audit_id}.pdf``.
    If the PDF was already generated (e.g. by a previous email dispatch), the
    stored copy is returned directly without re-rendering.

    Args:
        audit_id: The audit ID (== audit_id, or the public audit_id).
        db: Database session.

    Returns:
        FileResponse streaming the generated PDF.

    Raises:
        HTTPException 404: If the audit job does not exist.
    """
    logger.info(f"GET /reports/{audit_id}/download")

    job_repo = CrawlJobRepository(db)

    # Resolve by audit_id (CrawlJob.id) first; fall back to audit_id so callers
    # can use the public audit_id returned in CrawlResponse.
    job = await job_repo.get_by_id_or_audit_id(audit_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Audit job {audit_id} not found",
        )

    domain = urlparse(job.url).netloc or "unknown"
    output_path = (
        Path(settings.REPORT_OUTPUT_DIR) / domain / f"{str(audit_id)}.pdf"
    )

    # Reuse the stored copy if the PDF was already generated for this audit.
    if not output_path.exists():
        report = await build_audit_report(db, audit_id)
        render_audit_report_pdf(
            report,
            str(output_path),
            logo_url=settings.REPORT_LOGO_URL,
            company_name=settings.COMPANY_NAME,
            copyright_text=settings.COPYRIGHT_TEXT,
        )
        logger.info(
            f"GET /reports/{audit_id}/download: generated {output_path}"
        )
    else:
        logger.info(
            f"GET /reports/{audit_id}/download: returning existing {output_path}"
        )

    return FileResponse(
        path=str(output_path),
        media_type="application/pdf",
        filename=f"{domain}_seo_audit_report.pdf",
    )
