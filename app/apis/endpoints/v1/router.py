from fastapi import APIRouter

from app.apis.endpoints.v1.auth.router import router as auth_router
from app.apis.endpoints.v1.health.router import router as health_router
from app.apis.endpoints.v1.user.router import router as user_router

router = APIRouter()

router.include_router(auth_router, prefix="/auth", tags=["Auth"])
router.include_router(health_router, prefix="/health", tags=["Health"])
router.include_router(user_router, prefix="/user", tags=["User"])

