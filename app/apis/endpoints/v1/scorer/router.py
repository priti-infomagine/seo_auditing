"""
Scorer API Router.
"""
from fastapi import APIRouter

from app.apis.endpoints.v1.scorer.score import router as score_router

router = APIRouter()

router.include_router(score_router, prefix="", tags=["Scorer"])
