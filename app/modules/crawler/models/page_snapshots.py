"""
PageSnapshot model.

Fields:
    id, page_id, content, compressed, created_at, updated_at
"""
import uuid

from sqlalchemy import Boolean, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class PageSnapshot(TimestampMixin, Base):
    __tablename__ = "page_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("crawl_pages.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    compressed: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
    )

    def __repr__(self) -> str:
        return (
            f"<PageSnapshot "
            f"id={self.id} "
            f"page_id={self.page_id} "
            f"compressed={self.compressed} "
            f">"
        )
