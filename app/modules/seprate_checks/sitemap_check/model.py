import uuid

from sqlalchemy import Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class SitemapCheck(TimestampMixin, Base):
    """Persisted sitemap check payload used by paginated read endpoints."""

    __tablename__ = "sitemap_checks"

    __table_args__ = (
        Index("ix_sitemap_checks_url_created", "url", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)