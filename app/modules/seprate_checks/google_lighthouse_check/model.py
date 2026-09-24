import enum
import uuid

from sqlalchemy import Enum, Float, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class Device(str, enum.Enum):
    MOBILE = "mobile"
    DESKTOP = "desktop"


class PageStatus(str, enum.Enum):
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class LighthousePageResult(TimestampMixin, Base):
    __tablename__ = "lighthouse_page_results"

    __table_args__ = (
        # a retried task overwrites its row instead of creating a duplicate
        UniqueConstraint("check_id", "url", "device", name="uq_check_url_device"),
        Index("ix_lighthouse_check_id", "check_id"),
        Index("ix_lighthouse_domain_created", "domain", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    check_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    device: Mapped[Device] = mapped_column(Enum(Device), nullable=False)

    status: Mapped[PageStatus] = mapped_column(Enum(PageStatus), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # skip reason or error

    performance_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100
    seo_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100
    fcp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # First Contentful Paint
    lcp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Largest Contentful Paint
    tbt_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Total Blocking Time
    cls: Mapped[float | None] = mapped_column(Float, nullable=True)  # Cumulative Layout Shift
    recommendations: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
