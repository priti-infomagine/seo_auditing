import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base, TimestampMixin


class Subscription(TimestampMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plans.id"),
        nullable=False,
        index=True,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="active",
    )

    start_date: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    current_period_start: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    current_period_end: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
    )

    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    # Relationships
    plan = relationship("Plan", back_populates="subscriptions")
    user = relationship("User", back_populates="subscriptions")