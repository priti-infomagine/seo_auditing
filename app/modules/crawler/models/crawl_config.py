"""
CrawlConfig model.

This model exists only for Alembic migration compatibility.
The table will be dropped by migration d1e2f3a4b5c6.
Config is now stored in CrawlJob.crawl_config JSONB.
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class CrawlConfig(TimestampMixin, Base):
    __tablename__ = "crawl_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    crawl_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    max_depth: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=5,
    )
    max_pages: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1000,
    )
    concurrency: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
    )
    timeout_seconds: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
    )
    delay_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    follow_redirects: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    respect_robots: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlConfig "
            f"id={self.id} "
            f"crawl_id={self.crawl_id} "
            f"max_depth={self.max_depth}"
            f">"
        )