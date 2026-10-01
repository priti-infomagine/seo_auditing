import enum
import uuid

from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class MetaCheckStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MetaOverallStatus(str, enum.Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"


class MetaSeverity(str, enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class MetaCheck(TimestampMixin, Base):
    """Persisted multi-page metadata audit and its JSON result payload."""

    __tablename__ = "meta_checks"
    __table_args__ = (
        Index("ix_meta_checks_domain_created", "domain", "created_at"),
        Index("ix_meta_checks_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=MetaCheckStatus.QUEUED.value
    )
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    max_pages: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    pages: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    findings: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    overall_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0.0"
    )