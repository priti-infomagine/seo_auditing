"""
OTP model.

Stores one-time passwords for email verification.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OTPType(str, enum.Enum):
    REGISTER_OTP = "register_otp"
    FORGOT_PASS_OTP = "forgot_pass_otp"
    RESET_PASS_OTP = "reset_pass_otp"


class OTP(Base):
    __tablename__ = "otps"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    otp: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
    )

    otp_type: Mapped[OTPType] = mapped_column(
        Enum(
            OTPType,
            values_callable=lambda enum: [e.value for e in enum],
            name="otp_type_enum",
        ),
        nullable=False,
    )

    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<OTP "
            f"user_id={self.user_id} "
            f"type={self.otp_type}"
            f">"
        )