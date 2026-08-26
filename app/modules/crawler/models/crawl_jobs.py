"""
CrawlJob model.

Represents one audit/crawl execution. Crawl-level aggregate.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class CrawlJobStatus(str):
    QUEUED = "queued"
    CRAWLING = "crawling"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrawlJob(TimestampMixin, Base):
    __tablename__ = "crawl_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
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
        String(20),
        nullable=False,
        default=CrawlJobStatus.QUEUED,
    )
    crawl_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    max_pages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000,
    )
    max_depth: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    pages_discovered: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    pages_crawled: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    pages_failed: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    error_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    total_pages: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    current_page: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    progress_percent: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    crawl_config: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
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

    def __repr__(self) -> str:
        return (
            f"<CrawlJob "
            f"id={self.id} "
            f"user_id={self.user_id} "
            f"domain={self.domain} "
            f"status={self.status}"
            f">"
        )
