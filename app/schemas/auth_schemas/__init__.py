"""
Auth schemas package.
"""

from app.schemas.auth_schemas.register import RegisterRequest, RegisterResponse
from app.schemas.auth_schemas.verify_otp import (
    VerifyOTPRequest,
    VerifyOTPResponse,
)
from app.schemas.auth_schemas.login import LoginRequest, LoginResponse
from app.schemas.auth_schemas.refresh import RefreshTokenRequest, RefreshTokenResponse
from app.schemas.auth_schemas.logout import LogoutRequest, LogoutResponse
from app.schemas.auth_schemas.forgot_password import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    VerifyResetOTPRequest,
    VerifyResetOTPResponse,
)

__all__ = [
    "RegisterRequest",
    "RegisterResponse",
    "VerifyOTPRequest",
    "VerifyOTPResponse",
    "LoginRequest",
    "LoginResponse",
    "RefreshTokenRequest",
    "RefreshTokenResponse",
    "LogoutRequest",
    "LogoutResponse",
    "ForgotPasswordRequest",
    "ForgotPasswordResponse",
    "VerifyResetOTPRequest",
    "VerifyResetOTPResponse",
    "ResetPasswordRequest",
    "ResetPasswordResponse",
]
