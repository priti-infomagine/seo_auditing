"""
CrawlSiteData model.

Site-level information for a crawl job. One row per crawl.
Stores robots.txt, sitemaps, statistics, and duplicate clusters.
"""
import uuid

from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.database import TimestampMixin


class CrawlSiteData(TimestampMixin, Base):
    __tablename__ = "crawl_site_data"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    crawl_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    # --- JSONB columns ---
    robots: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    sitemaps: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    statistics: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    duplicate_clusters: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlSiteData "
            f"id={self.id} "
            f"crawl_job_id={self.crawl_job_id}"
            f">"
        )
