"""
Reports Celery tasks — handles async PDF generation and email delivery.
"""
from pathlib import Path
from uuid import UUID

from app.core.config import settings
from app.core.logger import logger
from app.modules.reports.services.pdf_generator import render_audit_report_pdf
from app.modules.reports.services.report_data_service import build_audit_report
from app.shared.services.email_service import send_email_sync
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


@celery_app.task(
    name="reports.send_audit_report_email",
    queue="email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def send_audit_report_email_task(audit_id: str, to_email: str) -> None:
    """
    Celery task: build report data, generate PDF, and email as attachment.

    Args:
        audit_id: Audit identifier (== crawl_id).
        to_email: Recipient email address.
    """
    logger.info(
        f"reports.send_audit_report_email: task started for audit_id={audit_id}, to_email={to_email}"
    )

    async def _build():
        from app.core.database import async_session_factory
        async with async_session_factory() as db:
            return await build_audit_report(db, UUID(audit_id))

    try:
        report = run_async(_build())

        safe_url = report.url.replace("://", "_").replace("/", "_")
        pdf_path = f"{settings.REPORT_OUTPUT_DIR}/{safe_url}_{audit_id}.pdf"

        rendered_path = render_audit_report_pdf(report, pdf_path)
        pdf_bytes = Path(rendered_path).read_bytes()

        subject = f"SEO Audit Report — {report.url}"
        content = (
            f"Hello,\n\n"
            f"Attached is your SEO Audit Report for {report.url}.\n"
            f"Overall Score: {report.overall_score.value if report.overall_score else 0:.1f} / 100 "
            f"(Grade: {report.overall_score.grade if report.overall_score else 'N/A'})\n\n"
            f"Best regards,\n"
            f"{settings.APP_NAME}"
        )
        attachment_filename = f"{safe_url}_seo_audit_report.pdf"

        send_email_sync(
            to_email=to_email,
            subject=subject,
            content=content,
            attachments=[(attachment_filename, pdf_bytes)],
        )

        logger.info(
            f"reports.send_audit_report_email: successfully sent report email for audit_id={audit_id} to {to_email}"
        )
    except Exception as exc:
        logger.error(
            f"reports.send_audit_report_email: failed for audit_id={audit_id}, to_email={to_email}: {exc}",
            exc_info=True,
        )
        raise
