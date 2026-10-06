import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class StreamingAuditStatus(str):
    QUEUED = "queued"
    PROCESSING = "processing"
    PARTIAL = "partial"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StreamingAuditRun(TimestampMixin, Base):
    __tablename__ = "streaming_audit_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    seed_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=StreamingAuditStatus.QUEUED)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    browser_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    request_timeout: Mapped[float] = mapped_column(Integer, nullable=False, default=30)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    queued_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    config: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    final_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<StreamingAuditRun id={self.id} status={self.status} domain={self.domain}>"
