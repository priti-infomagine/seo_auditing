"""
SeoAnalysisRun model.

One row per audit_id containing the aggregated SEO score.
The main tracking entity for the "SSEO Analyzer" pipeline.
"""
import uuid

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class SeoAnalysisRun(TimestampMixin, Base):
    __tablename__ = "seo_analysis_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    overall_score: Mapped[float] = mapped_column(
        Float,
        nullable=True,
    )
    grade: Mapped[str | None] = mapped_column(
        String(5),
        nullable=True,
    )
    total_pages_scored: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_rules_evaluated: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_passed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_failed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    critical_issues: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    warnings: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_pages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_summary: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    category_scores: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    top_issues: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    summary: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    output_file_path: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )
    analysis_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="pending",
    )
    scored_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<SeoAnalysisRun "
            f"id={self.id} "
            f"audit_id={self.audit_id} "
            f"domain={self.domain} "
            f"score={self.overall_score} "
            f"grade={self.grade}"
            f">"
        )
