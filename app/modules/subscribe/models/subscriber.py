"""
Subscriber model for newsletter subscriptions.
"""
import uuid
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Subscriber(TimestampMixin, Base):
    """Newsletter subscribers."""
    __tablename__ = "subscribers_list"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    def __repr__(self) -> str:
        return f"<Subscriber id={self.id} email={self.email}>"