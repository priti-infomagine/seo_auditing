"""
RuleEvaluationResult model.

Persistent store for every rule result produced by the rule engine
for every page. One row per (project, page, rule).
"""
import uuid

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, String, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class RuleEvaluationResult(TimestampMixin, Base):
    __tablename__ = "rule_evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    crawl_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    rule_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    rule_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    passed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    score_impact: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    recommendation: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    rule_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    tags: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "page_id", "rule_id",
            name="uq_rule_results_project_page_rule",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<RuleEvaluationResult "
            f"id={self.id} "
            f"project_id={self.project_id} "
            f"page_id={self.page_id} "
            f"rule_id={self.rule_id} "
            f"passed={self.passed} "
            f"severity={self.severity}"
            f">"
        )
