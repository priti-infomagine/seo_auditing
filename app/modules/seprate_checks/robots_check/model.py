import enum
import uuid

from sqlalchemy import Boolean, Enum, Index, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class FetchStatus(str, enum.Enum):
    SUCCESS = "success"
    NOT_FOUND = "not_found"
    UNREACHABLE = "unreachable"


class OverallStatus(str, enum.Enum):
    PASS = "pass"
    WARNING = "warning"
    FAIL = "fail"
    NOT_APPLICABLE = "not_applicable"


class Severity(str, enum.Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RobotCheck(TimestampMixin, Base):
    __tablename__ = "robot_check"

    __table_args__ = (
        Index("ix_robot_check_domain_checked", "domain", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    exists: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    fetch_status: Mapped[FetchStatus] = mapped_column(Enum(FetchStatus), nullable=False)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    user_agent_groups: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sitemaps_declared: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    sitemap_reachability: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    syntax_warnings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    findings: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)

    blocks_entire_site: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    blocks_assets: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    oversized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    overall_status: Mapped[OverallStatus] = mapped_column(Enum(OverallStatus), nullable=False)
    severity: Mapped[Severity] = mapped_column(Enum(Severity), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    why: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)

    check_version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
