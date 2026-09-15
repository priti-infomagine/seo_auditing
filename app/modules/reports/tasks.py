"""
Reports Celery tasks — handles async PDF generation and email delivery.
"""
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select

from app.core.config import settings
from app.core.datetime_utils import utc_now
from app.core.logger import logger
from app.modules.reports.services.pdf_generator import render_audit_report_pdf
from app.modules.reports.services.report_data_service import build_audit_report
from app.shared.services.email_service import send_email_sync
from app.shared.tasks.celery_app import celery_app
from app.shared.tasks.db import run_async


# Permanent archive root for domain-organized report storage
OUTPUT_ROOT = Path(__file__).resolve().parents[3] / "output" / "report"


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
        audit_id: Audit identifier (== audit_id).
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

        domain = urlparse(report.url).netloc or "unknown"
        pdf_path = f"{settings.REPORT_OUTPUT_DIR}/{domain}/{audit_id}.pdf"

        rendered_path = render_audit_report_pdf(
            report,
            pdf_path,
            logo_url=settings.REPORT_LOGO_URL,
            company_name=settings.COMPANY_NAME,
            copyright_text=settings.COPYRIGHT_TEXT,
        )
        pdf_bytes = Path(rendered_path).read_bytes()

        # Additionally store a permanent copy in output/report/{domain}/{audit_id}.pdf
        archive_path = OUTPUT_ROOT / domain / f"{audit_id}.pdf"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        archive_path.write_bytes(pdf_bytes)
        logger.info(f"Report archived at {archive_path}")

        subject = f"SEO Audit Report — {report.url}"
        content = (
            f"Hello,\n\n"
            f"Attached is your SEO Audit Report for {report.url}.\n"
            f"Overall Score: {report.overall_score.value if report.overall_score else 0:.1f} / 100 "
            f"(Grade: {report.overall_score.grade if report.overall_score else 'N/A'})\n\n"
            f"Best regards,\n"
            f"{settings.APP_NAME}"
        )
        attachment_filename = f"{domain}_seo_audit_report.pdf"

        send_email_sync(
            to_email=to_email,
            subject=subject,
            content=content,
            attachments=[(attachment_filename, pdf_bytes)],
        )

        logger.info(
            f"reports.send_audit_report_email: successfully sent report email for audit_id={audit_id} to {to_email}"
        )

        # Record the report in the DB (fire-and-forget via run_async)
        def _record():
            from app.core.database import async_session_factory
            from app.modules.reports.models.seo_report import SeoReport

            async def _do_record():
                async with async_session_factory() as db:
                    # Look up by the unique audit_id column (NOT the PK `id`);
                    # `db.get()` would query the primary key and always miss.
                    existing = (
                        await db.execute(
                            select(SeoReport).where(
                                SeoReport.audit_id == UUID(audit_id)
                            )
                        )
                    ).scalar_one_or_none()
                    if existing:
                        new_version = existing.report_version + 1
                        emails = list(existing.delivered_to)
                        if to_email not in emails:
                            emails.append(to_email)
                        existing.report_version = new_version
                        existing.delivered_to = emails
                        existing.delivered_at = utc_now().replace(tzinfo=None)
                        logger.info(
                            f"Updated SeoReport for audit_id={audit_id}, "
                            f"version={new_version}, delivered_to={emails}"
                        )
                    else:
                        db.add(SeoReport(
                            audit_id=UUID(audit_id),
                            report_version=1,
                            delivered_to=[to_email],
                            delivered_at=utc_now().replace(tzinfo=None),
                        ))
                        logger.info(
                            f"Created SeoReport for audit_id={audit_id}, "
                            f"version=1, delivered_to=[{to_email}]"
                        )
                    await db.commit()

            run_async(_do_record())

        try:
            _record()
        except Exception as db_exc:
            logger.error(
                f"Error recording SeoReport for audit_id={audit_id}: {db_exc}",
                exc_info=True,
            )
    except Exception as exc:
        logger.error(
            f"reports.send_audit_report_email: failed for audit_id={audit_id}, to_email={to_email}: {exc}",
            exc_info=True,
        )
        raise
