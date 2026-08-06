"""
User model.

Fields:
    id, name, email, password_hash, is_verified, created_at, updated_at
"""
import uuid

from sqlalchemy import Boolean, String ,Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.base import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    plan: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="free",
    )
    credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    model_config = {
        "from_attributes": True
    }

    def __repr__(self) -> str:
        return (
            f"<User "
            f"id={self.id} "
            f"email={self.email}"
            f">"
    )