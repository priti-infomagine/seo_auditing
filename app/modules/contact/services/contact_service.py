"""
Service layer for Contact Us form submission.
"""
from app.core.logger import logger
from app.modules.contact.schemas.contact import ContactRequest, ContactResponse
from app.modules.contact.utils.email_utils import send_contact_email


class ContactService:
    """Encapsulates contact form submission business logic."""

    def __init__(self):
        pass

    def execute(self, request: ContactRequest) -> ContactResponse:
        """
        Process contact form submission.

        Args:
            request: Validated contact form data

        Returns:
            ContactResponse with success message
        """
        logger.info(
            f"Contact form submitted: topic={request.topic}, from={request.email}"
        )

        # Dispatch email via Celery (fire-and-forget)
        send_contact_email(
            name=request.name,
            email=str(request.email),
            website=str(request.website) if request.website else None,
            topic=request.topic,
            message=request.message,
        )

        return ContactResponse()