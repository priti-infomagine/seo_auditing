"""
PageAsset model.

Fields:
    id, page_id, asset_type, url, mime_type, status_code, size_bytes, created_at, updated_at
"""
import uuid

from sqlalchemy import BigInteger, ForeignKey, SmallInteger, String, Text, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin


class PageAsset(TimestampMixin, Base):
    __tablename__ = "page_assets"

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
    asset_type: Mapped[str] = mapped_column(
        Enum("image", "css", "javascript", "font", "video", "pdf", "favicon", name="asset_type_enum"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    mime_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    status_code: Mapped[int | None] = mapped_column(
        SmallInteger,
        nullable=True,
    )
    size_bytes: Mapped[int | None] = mapped_column(
        BigInteger,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PageAsset "
            f"id={self.id} "
            f"page_id={self.page_id} "
            f"asset_type={self.asset_type} "
            f"url={self.url}"
            f">"
        )