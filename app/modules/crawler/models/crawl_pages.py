"""
CrawlPage model.

Central page table. One row per discovered/crawled URL.
High-frequency, queryable page facts.
"""
import hashlib
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class CrawlPage(TimestampMixin, Base):
    __tablename__ = "crawl_pages"

    __table_args__ = (
        UniqueConstraint("crawl_id", "normalized_url", name="uq_crawl_pages_crawl_id_normalized_url"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    crawl_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    parent_page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
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
    url_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    scheme: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    host: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    path: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    query: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
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
    content_length: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )
    response_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    is_internal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    is_crawled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_success: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_redirect: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_error: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
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
