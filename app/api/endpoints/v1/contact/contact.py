"""
POST /contact — Submit contact form.
"""
from fastapi import APIRouter, HTTPException, status

from app.core.logger import logger
from app.modules.contact.schemas.contact import ContactRequest, ContactResponse
from app.modules.contact.services.contact_service import ContactService

router = APIRouter()


@router.post(
    "/",
    response_model=ContactResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit contact form",
    responses={
        201: {"description": "Message sent successfully"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error (email queue failure)"},
    },
)
async def submit_contact(
    body: ContactRequest,
) -> ContactResponse:
    """Submit a contact form message. Sends email notification via async queue."""
    logger.info("POST /contact - Contact form submission received")
    try:
        service = ContactService()
        return service.execute(body)
    except Exception as exc:
        logger.error(f"Contact form submission failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process contact form. Please try again later.",
        )