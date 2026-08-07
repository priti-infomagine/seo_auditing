"""
Service layer for user registration.

Steps:
    1. Validate input & check duplicate email
    2. Hash password
    3. Create user with is_verified=False
    4. Generate 6-digit OTP
    5. Store OTP in DB
    6. Return success (OTP sent)
"""
import random
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.models.otp import OTP, OTPType
from app.modules.auth.models.users import User
from app.modules.auth.schemas.register import RegisterRequest, RegisterResponse
from app.core.security import hash_password
from app.modules.auth.utils.email_utils import send_register_otp_email


class RegisterService:
    """Encapsulates registration business logic."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def execute(self, request: RegisterRequest) -> RegisterResponse:
        # ── 1. Duplicate email check ────────────────────────────────────
        existing = await self.db.execute(
            select(User).where(User.email == request.email)
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A user with this email already exists.",
            )

        # ── 2. Hash password ───────────────────────────────────────────
        hashed_pw = hash_password(request.password)

        # ── 3. Create user (unverified) ────────────────────────────────
        user = User(
            id=uuid.uuid4(),
            name=request.name,
            email=request.email,
            password_hash=hashed_pw,
            is_verified=False,
        )
        self.db.add(user)
        await self.db.flush()

        # # ── 4. Generate 6-digit OTP ────────────────────────────────────
        
        from app.modules.auth.utils.auth_utils import generate_otp_code
        otp_code, expires_at = generate_otp_code()
            
        otp = OTP(
            id=uuid.uuid4(),
            user_id=user.id,
            otp=otp_code,
            otp_type=OTPType.REGISTER_OTP,
            expires_at=expires_at,
        )
        self.db.add(otp)
        await self.db.flush()

        # ── NOTE: In production, send OTP via email/SMS here through background tasks ───────────
        
        await send_register_otp_email(user.email, otp_code)
        print(f"[REGISTER] OTP for {user.email}: {otp_code}")

        # ── 5. Return success ──────────────────────────────────────────
        return RegisterResponse(message="OTP sent successfully")