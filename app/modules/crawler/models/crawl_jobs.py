"""
CrawlJob model.

Fields:
    id, user_id, domain, status, started_at, completed_at, duration_ms,
    created_at, updated_at
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.database import TimestampMixin


class CrawlJob(TimestampMixin, Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(
        String(2048),
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Enum("queued", "crawling", "completed", "failed", "cancelled", name="crawl_job_status_enum"),
        nullable=False,
        default="queued",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    duration_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    error: Mapped[str | None] = mapped_column(
        String(1024),
        nullable=True,
    )

    crawl_config: Mapped["CrawlConfig"] = relationship(
        "CrawlConfig",
        back_populates="crawl_job",
        uselist=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlJob "
            f"id={self.id} "
            f"user_id={self.user_id} "
            f"domain={self.domain} "
            f"status={self.status}"
            f">"
        )