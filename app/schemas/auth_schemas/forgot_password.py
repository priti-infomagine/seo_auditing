"""
Schemas for password reset flow.

Endpoints:
    POST /auth/forgot-password  → Request OTP
    POST /auth/verify-reset-otp → Verify OTP
    POST /auth/reset-password   → Reset password
"""
import re

from pydantic import BaseModel, EmailStr, field_validator


# ── Forgot Password (Request OTP) ────────────────────────────────────────────

class ForgotPasswordRequest(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Email is required.")
        return v.strip().lower()


class ForgotPasswordResponse(BaseModel):
    message: str


# ── Verify Reset OTP ─────────────────────────────────────────────────────────

class VerifyResetOTPRequest(BaseModel):
    email: EmailStr
    otp: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Email is required.")
        return v.strip().lower()

    @field_validator("otp")
    @classmethod
    def validate_otp(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("OTP is required.")
        if not re.match(r"^\d{6}$", v.strip()):
            raise ValueError("OTP must be a 6-digit number.")
        return v.strip()


class VerifyResetOTPResponse(BaseModel):
    message: str


# ── Reset Password ───────────────────────────────────────────────────────────

class ResetPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str
    confirm_password: str

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Email is required.")
        return v.strip().lower()

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("New password is required.")
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long.")
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter.")
        if not re.search(r"[a-z]", v):
            raise ValueError("Password must contain at least one lowercase letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit.")
        if not re.search(r"[!@#$%^&*(),.?\":{}|<>_\-+=\[\]\\;'/`~]", v):
            raise ValueError("Password must contain at least one special character.")
        return v

    @field_validator("confirm_password")
    @classmethod
    def validate_confirm_password(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Confirm password is required.")
        return v

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v: str, info) -> str:
        if "new_password" in info.data and v != info.data["new_password"]:
            raise ValueError("Passwords do not match.")
        return v


class ResetPasswordResponse(BaseModel):
    message: str