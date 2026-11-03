"""
Subscribe Celery tasks — handles async email delivery for subscriptions.
"""
from app.core.config import settings
from app.core.logger import logger
from app.shared.services.email_service import send_email_sync
from app.shared.tasks.celery_app import celery_app


@celery_app.task(
    name="subscribe.send_subscription_confirmation",
    queue="email",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def send_subscription_confirmation_task(email: str) -> None:
    """Send subscription confirmation email to the user."""
    logger.info(f"subscribe.send_subscription_confirmation: task started for {email}")

    subject = f"Welcome to {settings.APP_NAME} Newsletter"

    content = (
        f"Hello,\n\n"
        f"Thanks for subscribing to {settings.APP_NAME}!\n\n"
        f"We'll send you updates and new product launches.\n\n"
        f"Best regards,\n"
        f"The {settings.APP_NAME} Team"
    )

    try:
        send_email_sync(to_email=email, subject=subject, content=content)
        logger.info(f"Subscription confirmation sent to {email}")
    except Exception as exc:
        logger.error(f"Failed to send subscription confirmation to {email}: {exc}", exc_info=True)
        raise