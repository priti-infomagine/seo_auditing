import uuid

from sqlalchemy import Enum, Index, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.modules.seprate_checks.robots_check.model import (
    FetchStatus,
    OverallStatus,
    Severity,
)

__all__ = [
    "FetchStatus",
    "OverallStatus",
    "Severity",
    "SitemapCheck",
]


class SitemapCheck(TimestampMixin, Base):
    """Persisted sitemap check result."""

    __tablename__ = "sitemap_checks"

    __table_args__ = (
        Index("ix_sitemap_checks_domain_created", "domain", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    robots_fetch_status: Mapped[FetchStatus] = mapped_column(
        Enum(FetchStatus), nullable=False
    )
    robots_status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    robots_final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_robots_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    sitemaps_declared: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    sitemap_results: Mapped[list[dict]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    findings: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    overall_status: Mapped[OverallStatus] = mapped_column(
        Enum(OverallStatus), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0.0"
    )