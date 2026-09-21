"""
UrlIgnorePattern model.

Single polymorphic table for both pattern definitions (record_type='pattern')
and skip audit trail (record_type='skip').
"""
import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class UrlIgnorePattern(TimestampMixin, Base):
    __tablename__ = "url_ignore_patterns"

    __table_args__ = (
        CheckConstraint(
            "record_type IN ('pattern', 'skip')",
            name="chk_record_type"
        ),
        CheckConstraint(
            "scope IN ('global', 'performance', 'accessibility', 'bestpractices', 'seo', 'runtime')",
            name="chk_scope"
        ),
        CheckConstraint(
            "match_type IN ('path', 'prefix', 'extension', 'query_param', 'regex', 'scheme', 'host') OR match_type IS NULL",
            name="chk_match_type"
        ),
        CheckConstraint(
            "(record_type = 'pattern' AND ((match_type IS NOT NULL AND pattern IS NOT NULL) OR scope IN ('performance', 'accessibility', 'bestpractices', 'seo'))) OR (record_type = 'skip' AND audit_id IS NOT NULL AND url IS NOT NULL)",
            name="chk_pattern_fields"
        ),
        Index(
            "ix_url_ignore_patterns_lookup",
            "scope", "is_active", "sort_order",
            postgresql_where="record_type = 'pattern' AND is_active = TRUE"
        ),
        Index(
            "ix_url_ignore_patterns_skips_audit",
            "audit_id",
            postgresql_where="record_type = 'skip'"
        ),
        Index(
            "ix_url_ignore_patterns_skips_reason",
            "audit_id", "reason",
            postgresql_where="record_type = 'skip'"
        ),
        Index(
            "ix_url_ignore_patterns_skips_matched",
            "matched_pattern_id",
            postgresql_where="record_type = 'skip'"
        ),
        Index(
            "ix_url_ignore_patterns_unique",
            "scope", "match_type", "pattern",
            unique=True,
            postgresql_where="record_type = 'pattern'"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    record_type: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    scope: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    match_type: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
    )
    pattern: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=sa.text("true"),
    )
    is_default: Mapped[bool] = mapped_column(
        nullable=False,
        server_default=sa.text("true"),
    )
    sort_order: Mapped[int] = mapped_column(
        nullable=False,
        server_default=sa.text("0"),
    )
    audit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=True,
    )
    url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    normalized_url: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    matched_pattern_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("url_ignore_patterns.id"),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    def __repr__(self) -> str:
        if self.record_type == "pattern":
            return f"<UrlIgnorePattern id={self.id} scope={self.scope} match_type={self.match_type} pattern={self.pattern}>"
        return f"<UrlIgnorePattern id={self.id} record_type=skip audit_id={self.audit_id} reason={self.reason}>"