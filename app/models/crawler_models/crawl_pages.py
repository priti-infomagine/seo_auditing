"""
CrawlPage model.

Fields:
    id, crawl_id, parent_page_id, url, normalized_url, depth, status_code, final_url,
    content_type, content_size, response_time_ms, checksum, discovered_at, crawled_at,
    created_at, updated_at
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, SmallInteger, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class CrawlPage(TimestampMixin, Base):
    __tablename__ = "crawl_pages"

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
    parent_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    normalized_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    depth: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    status_code: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )
    final_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    content_size: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    response_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    checksum: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=True,
    )
    crawled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlPage "
            f"id={self.id} "
            f"crawl_id={self.crawl_id} "
            f"url={self.url} "
            f"depth={self.depth}"
            f">"
        )