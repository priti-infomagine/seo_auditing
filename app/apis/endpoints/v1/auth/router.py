"""
Auth routes — aggregated router.

Mounts all auth sub-routers under their respective prefixes.
"""
from fastapi import APIRouter

from app.apis.endpoints.v1.auth.register import router as register_router
from app.apis.endpoints.v1.auth.login import router as login_router
from app.apis.endpoints.v1.auth.verify_otp import router as verify_otp_router
from app.apis.endpoints.v1.auth.refresh_token import router as refresh_router
from app.apis.endpoints.v1.auth.logout import router as logout_router
from app.apis.endpoints.v1.auth.forgot_pass import router as password_reset_router

router = APIRouter()

router.include_router(register_router, prefix="/register")
# router.include_router(login_router, prefix="/login")
router.include_router(verify_otp_router, prefix="/verify-otp")
router.include_router(refresh_router, prefix="/refresh")

router.include_router(logout_router, prefix="/logout")
router.include_router(password_reset_router, prefix="/forgot-pass")