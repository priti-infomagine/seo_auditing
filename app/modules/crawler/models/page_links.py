"""
PageLink model.

Fields:
    id, page_id, target_url, anchor_text, rel, is_internal, is_nofollow, link_type, created_at, updated_at
"""
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, String, Text
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
        ForeignKey("crawl_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    anchor_text: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    rel: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    is_internal: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    is_nofollow: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )
    link_type: Mapped[str] = mapped_column(
        Enum(
            "anchor",
            "image",
            "script",
            "stylesheet",
            "canonical",
            "hreflang",
            name="link_type_enum",
        ),
        nullable=False,
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