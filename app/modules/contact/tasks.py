"""
Contact Celery tasks — handles async email delivery for contact form submissions.
"""
from app.core.config import settings
from app.core.logger import logger
from app.shared.services.email_service import send_email_sync
from app.shared.tasks.celery_app import celery_app


@celery_app.task(
    name="contact.send_contact_email",
    queue="email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def send_contact_email_task(
    name: str,
    email: str,
    website: str | None,
    topic: str,
    message: str,
) -> None:
    """
    Celery task: send contact form confirmation email to the user.

    Args:
        name: Sender's name
        email: Sender's email (recipient of this confirmation)
        website: Sender's website (optional)
        topic: Contact topic
        message: Contact message
    """
    logger.info(
        f"contact.send_contact_email: task started for topic={topic}, to={email}"
    )

    subject = f"Thank you for contacting {settings.APP_NAME}"

    website_line = f"\nWebsite: {website}" if website else ""

    content = (
        f"Hello {name},\n\n"
        f"Thank you for reaching out to us. We have received your message:\n\n"
        f"Topic: {topic}\n"
        f"Message: {message}{website_line}\n\n"
        f"Our team will connect with you within 2-3 working days.\n\n"
        f"Best regards,\n"
        f"The {settings.APP_NAME} Team"
    )

    try:
        send_email_sync(
            to_email=email,
            subject=subject,
            content=content,
        )
        logger.info(
            f"contact.send_contact_email: successfully sent confirmation email to {email}"
        )
    except Exception as exc:
        logger.error(
            f"contact.send_contact_email: failed for to={email}: {exc}",
            exc_info=True,
        )
        raise