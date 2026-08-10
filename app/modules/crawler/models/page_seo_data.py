"""
PageSEOData model.

One row per crawled HTML page. Stores SEO-relevant extracted data.
Uses JSONB for heterogeneous/nested facts, normal columns for frequently queried fields.
"""
import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class PageSEOData(TimestampMixin, Base):
    __tablename__ = "page_seo_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    # --- Normal columns for frequent queries ---
    title: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    title_length: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    meta_description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    meta_description_length: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    canonical: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    robots_meta: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    language: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )
    charset: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    viewport: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    favicon: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    word_count: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    # --- JSONB columns for structured/nested data ---
    page_metadata: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    headings: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    content: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    structured_data: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    social: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    indexability: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    accessibility: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PageSEOData "
            f"id={self.id} "
            f"page_id={self.page_id} "
            f"title={self.title!r}"
            f">"
        )
