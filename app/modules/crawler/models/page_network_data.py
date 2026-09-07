"""
PageNetworkData model.

One row per page. Stores network response, redirects, security, and performance data.
"""
import uuid

from sqlalchemy import Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class PageNetworkData(TimestampMixin, Base):
    __tablename__ = "page_network_data"

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
    # --- Response (normal columns) ---
    status_code: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    content_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    content_length: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    response_time_ms: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    # --- JSONB columns ---
    headers: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    redirects: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    security: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    performance: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<PageNetworkData "
            f"id={self.id} "
            f"page_id={self.page_id} "
            f"status_code={self.status_code}"
            f">"
        )
