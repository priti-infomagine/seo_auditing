"""SERP rank check DB models.

Two tables that are intentionally kept (but no longer referenced
by FK from ``rank_checks``):

- ``serp_locations`` — reference table of DataForSEO Google locations
  (retained for backward compatibility / inspection).
- ``serp_languages`` — reference table of DataForSEO Google languages
  (retained for backward compatibility / inspection).

Primary table:

- ``rank_checks`` — one row per rank-check job. Postgres is the only
  source of truth: a partial unique index on
  ``(COALESCE(user_id, anon), fingerprint)`` for in-flight rows
  provides duplicate protection without Redis.  ``user_id`` is
  nullable so that anonymous (public) API callers can still create
  checks; the COALESCE collapses all anonymous rows to a single
  constant UUID so the fingerprint alone de-duplicates them.

Location and language are now stored as **names** (strings) rather
than integer codes — DataForSEO accepts ``location_name`` and
``language_name`` directly, so no reference-table lookup is needed.
"""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    Numeric,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin

# Placeholder UUID used in the COALESCE-based unique index so that
# anonymous (user_id IS NULL) checks are still de-duplicated by
# fingerprint just like authenticated ones.
ANONYMOUS_USER_ID: uuid.UUID = uuid.UUID(
    "00000000-0000-0000-0000-000000000000"
)


class RankCheckStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    RANKED = "ranked"
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
            text(f"COALESCE(user_id, '{ANONYMOUS_USER_ID}'::uuid)"),
            "fingerprint",
            unique=True,
            postgresql_where=text("status IN ('queued','running')"),
        ),
        Index("ix_rank_checks_user_created", "user_id", "created_at"),
        Index("ix_rank_checks_created_at", "created_at"),
        CheckConstraint(
            "device IN ('desktop','mobile')",
            name="ck_rank_checks_device",
        ),
        CheckConstraint(
            "depth >= 10 AND depth <= 200",
            name="ck_rank_checks_depth",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
        index=True,
    )
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    location_name: Mapped[str] = mapped_column(Text, nullable=False)
    language_name: Mapped[str] = mapped_column(Text, nullable=False)
    device: Mapped[str] = mapped_column(Text, nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False)
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

    def __repr__(self) -> str:
        return (
            f"<RankCheck id={self.id} status={self.status!r} "
            f"keyword={self.keyword!r} domain={self.domain!r}>"
        )
