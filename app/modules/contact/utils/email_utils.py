"""
Email utility functions for Contact module.
"""
from app.modules.contact.tasks import send_contact_email_task


def send_contact_email(
    name: str,
    email: str,
    website: str | None,
    topic: str,
    message: str,
) -> None:
    """
    Dispatch contact form confirmation email via Celery task.

    Args:
        name: Sender's name
        email: Sender's email (recipient of confirmation)
        website: Sender's website (optional)
        topic: Contact topic
        message: Contact message
    """
    send_contact_email_task.delay(name, email, website, topic, message)