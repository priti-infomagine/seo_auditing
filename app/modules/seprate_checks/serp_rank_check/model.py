"""SERP rank check DB models.

Three tables:

- ``serp_locations`` — reference table of DataForSEO Google locations.
- ``serp_languages`` — reference table of DataForSEO Google languages.
- ``rank_checks`` — one row per rank-check job. Postgres is the only
  source of truth: a partial unique index on ``(user_id, fingerprint)``
  for in-flight rows provides duplicate protection without Redis.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class RankCheckStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RANKED = "ranked"
    DONE = "done"
    FAILED = "failed"


class PreviewStatus(str, enum.Enum):
    NONE = "none"
    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"


class SerpLocation(Base):
    __tablename__ = "serp_locations"

    location_code: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    country_iso: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_type: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SerpLocation code={self.location_code} "
            f"name={self.name!r}>"
        )


class SerpLanguage(Base):
    __tablename__ = "serp_languages"

    language_code: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    def __repr__(self) -> str:
        return f"<SerpLanguage code={self.language_code!r}>"


class RankCheck(TimestampMixin, Base):
    __tablename__ = "rank_checks"

    __table_args__ = (
        Index(
            "uq_rank_checks_inflight",
            "user_id",
            "fingerprint",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
        Index("ix_rank_checks_user_created", "user_id", "created_at"),
        CheckConstraint(
            "device IN ('desktop','mobile')",
            name="ck_rank_checks_device",
        ),
        CheckConstraint(
            "depth IN (10,20,50,100)",
            name="ck_rank_checks_depth",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    location_code: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("serp_locations.location_code"),
        nullable=False,
    )
    language_code: Mapped[str] = mapped_column(
        Text,
        ForeignKey("serp_languages.language_code"),
        nullable=False,
    )
    device: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
    include_preview: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )
    fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=RankCheckStatus.QUEUED.value,
    )
    provider_called_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    provider_cost: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 5),
        nullable=True,
    )
    raw_response: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default=PreviewStatus.NONE.value,
    )
    preview_html_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    preview_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RankCheck id={self.id} status={self.status!r} "
            f"keyword={self.keyword!r} domain={self.domain!r}>"
        )
