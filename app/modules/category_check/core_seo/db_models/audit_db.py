"""
AuditCheck SQLAlchemy model for persisting Core SEO audit results to the database.

This is the single DB model for the Core SEO module. It stores audit-level
information that persists across sessions, supporting the write-behind
policy where Redis acts as a fast buffer and the DB is updated asynchronously.
"""
from __future__ import annotations

import enum
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Enum, Integer, String, Text, func

from app.core.database import Base


class AuditStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuditCheck(Base):
    """Persisted record of a Core SEO audit.

    Mirrors the audit state that EventBus maintains in Redis, but with
    TTL-less persistence for historical reporting. Uses a write-behind
    policy: Redis is updated immediately for real-time visibility, while
    the DB record is flushed asynchronously after the audit completes.

    Attributes:
        audit_id: Unique identifier for the audit (primary key).
        start_url: The seed URL the audit started from.
        status: Current audit status (pending/running/completed/failed).
        total_pages: Number of pages discovered.
        crawled_pages: Number of pages successfully crawled.
        pages_failed: Number of pages that failed during crawling.
        overall_score: Aggregate SEO score across all pages.
        grade: Letter grade (A+ ... F).
        started_at: When the audit began.
        completed_at: When the audit finished (nullable until complete).
        report_json: Serialized audit report (stored as JSON text).
        error_message: Error details if the audit failed.
    """

    __tablename__ = "core_seo_audit_checks"

    __table_args__ = {"extend_existing": True, "sqlite_autoincrement": False}

    audit_id: str = Column(String(64), primary_key=True, index=True)
    start_url: str = Column(String(2048), nullable=False, index=True)
    status: AuditStatus = Column(
        Enum(AuditStatus, name="audit_status"),
        default=AuditStatus.PENDING,
        nullable=False,
    )
    total_pages: int = Column(Integer, default=0, nullable=False)
    crawled_pages: int = Column(Integer, default=0, nullable=False)
    pages_failed: int = Column(Integer, default=0, nullable=False)
    overall_score: float = Column(Integer, default=0, nullable=False)
    grade: str = Column(String(4), default="F", nullable=False)
    started_at: datetime = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    completed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    report_json: str | None = Column(Text, nullable=True)
    error_message: str | None = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AuditCheck audit_id={self.audit_id!r} status={self.status!r} "
            f"score={self.overall_score} grade={self.grade!r}>"
        )

    def set_report(self, report: dict[str, Any]) -> None:
        """Serialize and store the full audit report as JSON."""
        self.report_json = json.dumps(report, default=str)

    def get_report(self) -> dict[str, Any] | None:
        """Deserialize and return the stored audit report."""
        if not self.report_json:
            return None
        try:
            return json.loads(self.report_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def mark_completed(
        self,
        overall_score: float,
        grade: str,
        crawled_pages: int = 0,
        total_pages: int = 0,
        pages_failed: int = 0,
        report: dict[str, Any] | None = None,
    ) -> None:
        """Mark the audit as completed with final metrics."""
        self.status = AuditStatus.COMPLETED
        self.overall_score = overall_score
        self.grade = grade
        self.crawled_pages = crawled_pages
        self.total_pages = total_pages
        self.pages_failed = pages_failed
        self.completed_at = func.now()
        if report is not None:
            self.set_report(report)

    def mark_failed(self, error_message: str) -> None:
        """Mark the audit as failed."""
        self.status = AuditStatus.FAILED
        self.error_message = error_message
        self.completed_at = func.now()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model to a dictionary for API responses."""
        return {
            "audit_id": self.audit_id,
            "start_url": self.start_url,
            "status": self.status.value if self.status else None,
            "total_pages": self.total_pages,
            "crawled_pages": self.crawled_pages,
            "pages_failed": self.pages_failed,
            "overall_score": self.overall_score,
            "grade": self.grade,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


__all__ = ["AuditCheck", "AuditStatus"]
