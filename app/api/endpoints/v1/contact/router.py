"""
Contact routes — aggregated router.
"""
from fastapi import APIRouter

from app.api.endpoints.v1.contact.contact import router as contact_router

router = APIRouter()

router.include_router(contact_router, prefix="", tags=["Contact"])