import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class StreamingPageResult(TimestampMixin, Base):
    __tablename__ = "streaming_page_results"
    __table_args__ = (
        UniqueConstraint("audit_id", "normalized_url", name="uq_streaming_page_result_audit_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    normalized_url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="completed")
    page_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    processing_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parsed_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    page_findings: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    discovered_urls: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    error_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<StreamingPageResult audit_id={self.audit_id} url={self.normalized_url} status={self.processing_status}>"
