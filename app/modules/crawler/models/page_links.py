"""
PageLink model.

Represents a link from one page to another.
Expanded with target lookup fields, rel attributes, and crawl-level queryability.
"""
import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class PageLink(TimestampMixin, Base):
    __tablename__ = "page_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    target_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    normalized_target_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    anchor_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    rel: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    link_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    is_internal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    is_external: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    nofollow: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    ugc: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    sponsored: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    is_crawlable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    target_status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    target_response_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    target_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PageLink "
            f"id={self.id} "
            f"page_id={self.page_id} "
            f"link_type={self.link_type} "
            f"target_url={self.target_url}"
            f">"
        )
