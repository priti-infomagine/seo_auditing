import enum
import uuid

from sqlalchemy import Enum, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.modules.seprate_checks.robots_check.model import (
    FetchStatus,
)

__all__ = [
    "FetchStatus",
    "OverallStatus",
    "Severity",
    "SitemapCheckStatus",
    "SitemapOverallStatus",
    "SitemapSeverity",
    "SitemapCheck",
]


class SitemapCheckStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class SitemapOverallStatus(str, enum.Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class SitemapSeverity(str, enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Aliases for helper modules
OverallStatus = SitemapOverallStatus
Severity = SitemapSeverity


class SitemapCheck(TimestampMixin, Base):
    """Persisted sitemap check task and result."""

    __tablename__ = "sitemap_checks"

    __table_args__ = (
        Index("ix_sitemap_checks_domain_created", "domain", "created_at"),
        Index("ix_sitemap_checks_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=SitemapCheckStatus.QUEUED.value
    )
    task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    progress: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Robots.txt and sitemap data (from migration 07c3d4e5f6a7)
    robots_fetch_status: Mapped[FetchStatus] = mapped_column(
        Enum(FetchStatus, name="fetchstatus", create_type=False, validate_strings=True),
        nullable=False
    )
    robots_status_code: Mapped[int | None] = mapped_column(nullable=True)
    robots_final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_robots_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sitemaps_declared: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    sitemap_results: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    # Evaluation results - use existing DB enum types
    overall_status: Mapped[SitemapOverallStatus | None] = mapped_column(
        Enum(SitemapOverallStatus, name="overallstatus", create_type=False, validate_strings=True),
        nullable=True
    )
    severity: Mapped[SitemapSeverity | None] = mapped_column(
        Enum(SitemapSeverity, name="severity", create_type=False, validate_strings=True),
        nullable=True
    )
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sitemaps: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    findings: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    recommendations: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="2.0.0"
    )