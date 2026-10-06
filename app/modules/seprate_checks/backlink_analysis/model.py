import enum
import uuid

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class BacklinkCheckStatus(str, enum.Enum):
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class BacklinkCheck(TimestampMixin, Base):
    __tablename__ = "backlink_checks"
    __table_args__ = (
        Index("ix_backlink_checks_target_created", "target", "created_at"),
        Index("ix_backlink_checks_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    target: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BacklinkCheckStatus.PROCESSING.value
    )
    evidence_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    result: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
