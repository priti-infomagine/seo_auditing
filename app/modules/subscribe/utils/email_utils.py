"""
Email utility functions for Subscribe module.
"""
from app.modules.subscribe.tasks import send_subscription_confirmation_task


def send_subscription_confirmation(email: str) -> None:
    """Dispatch subscription confirmation email via Celery task."""
    send_subscription_confirmation_task.delay(email)