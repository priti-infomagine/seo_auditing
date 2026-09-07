"""
PageResource model.

One row per discovered resource (image, CSS, JS, font, iframe, etc.).
1:N with crawl_pages. Replaces page_assets.
"""
import uuid

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class PageResource(TimestampMixin, Base):
    __tablename__ = "page_resources"

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
    resource_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    normalized_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    size_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    # --- Image-specific (nullable for non-images) ---
    alt: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    width: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    height: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    loading: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )
    srcset: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    sizes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    is_lazy: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    is_mixed_content: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    # --- Extra JSONB for future resource attributes ---
    extra: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PageResource "
            f"id={self.id} "
            f"page_id={self.page_id} "
            f"type={self.resource_type} "
            f"url={self.url}"
            f">"
        )
