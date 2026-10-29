"""
ContentAuditCheck SQLAlchemy model for persisting Content audit results.

Mirrors core_seo's AuditCheck but uses a separate table
(content_audit_checks) and its own ContentAuditStatus enum, so that
content and core_seo audits are independently queryable.

Shared audit_id: both core_seo_audit_checks and content_audit_checks
share the same audit_id column value, allowing cross-category joins.
"""
from __future__ import annotations

import enum
import json
from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, Enum, Float, Integer, String, Text, func

from app.core.database import Base


class ContentAuditStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ContentAuditCheck(Base):
    """Persisted record of a Content audit.

    Mirrors the audit state that ContentEventBus maintains in Redis,
    but with TTL-less persistence for historical reporting. Uses a
    write-behind policy: Redis is updated immediately for real-time
    visibility, while the DB record is flushed asynchronously.
    """

    __tablename__ = "content_audit_checks"

    __table_args__ = {"extend_existing": True, "sqlite_autoincrement": False}

    audit_id: str = Column(String(64), primary_key=True, index=True)
    start_url: str = Column(String(2048), nullable=False, index=True)
    status: ContentAuditStatus = Column(
        Enum(ContentAuditStatus, name="content_audit_status"),
        default=ContentAuditStatus.PENDING,
        nullable=False,
    )
    total_pages: int = Column(Integer, default=0, nullable=False)
    crawled_pages: int = Column(Integer, default=0, nullable=False)
    pages_failed: int = Column(Integer, default=0, nullable=False)
    rules_passed: int = Column(Integer, default=0, nullable=False)
    rules_failed: int = Column(Integer, default=0, nullable=False)
    pass_percentage: float = Column(Float, default=0.0, nullable=False)
    started_at: datetime = Column(DateTime(timezone=True), default=func.now(), nullable=False)
    completed_at: datetime | None = Column(DateTime(timezone=True), nullable=True)
    report_json: str | None = Column(Text, nullable=True)
    error_message: str | None = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ContentAuditCheck audit_id={self.audit_id!r} status={self.status!r} "
            f"rules_passed={self.rules_passed} rules_failed={self.rules_failed}>"
        )

    def set_report(self, report: dict[str, Any]) -> None:
        self.report_json = json.dumps(report, default=str)

    def get_report(self) -> dict[str, Any] | None:
        if not self.report_json:
            return None
        try:
            return json.loads(self.report_json)
        except (json.JSONDecodeError, TypeError):
            return None

    def mark_completed(
        self,
        rules_passed: int = 0,
        rules_failed: int = 0,
        pass_percentage: float = 0.0,
        crawled_pages: int = 0,
        total_pages: int = 0,
        pages_failed: int = 0,
        report: dict[str, Any] | None = None,
    ) -> None:
        self.status = ContentAuditStatus.COMPLETED
        self.rules_passed = rules_passed
        self.rules_failed = rules_failed
        self.pass_percentage = pass_percentage
        self.crawled_pages = crawled_pages
        self.total_pages = total_pages
        self.pages_failed = pages_failed
        self.completed_at = func.now()
        if report is not None:
            self.set_report(report)

    def mark_failed(self, error_message: str) -> None:
        self.status = ContentAuditStatus.FAILED
        self.error_message = error_message
        self.completed_at = func.now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "audit_id": self.audit_id,
            "start_url": self.start_url,
            "status": self.status.value if self.status else None,
            "total_pages": self.total_pages or 0,
            "crawled_pages": self.crawled_pages or 0,
            "pages_failed": self.pages_failed or 0,
            "rules_passed": self.rules_passed or 0,
            "rules_failed": self.rules_failed or 0,
            "pass_percentage": self.pass_percentage or 0.0,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error_message": self.error_message,
        }


__all__ = ["ContentAuditCheck", "ContentAuditStatus"]
