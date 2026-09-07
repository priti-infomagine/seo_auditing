"""
CrawlError model.

Fields:
    id, crawl_id, page_id, error_type, error_message,
    created_at, updated_at
"""
import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class CrawlError(TimestampMixin, Base):
    __tablename__ = "crawl_errors"

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
    page_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_pages.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    error_type: Mapped[str] = mapped_column(
        Enum(
            "fetch_error",
            "crawl_error",
            "parse_error",
            "timeout",
            "connection_error",
            "robots_error",
            "network_error",
            name="crawl_error_type_enum",
        ),
        nullable=False,
    )
    error_message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlError "
            f"id={self.id} "
            f"crawl_id={self.crawl_id} "
            f"error_type={self.error_type} "
            f"error_message={self.error_message[:50]} "
            f">"
        )
