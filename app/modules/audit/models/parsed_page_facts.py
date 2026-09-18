"""
ParsedPageFact model.

Persistent store for ParsedPage objects. One row per page per audit.
Stores the full parsed data alongside flat page facts, structured elements,
and element attributes for efficient querying.
"""
import uuid

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class ParsedPageFact(TimestampMixin, Base):
    __tablename__ = "parsed_page_facts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    parsed_data: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    page_facts: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )
    elements: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    attributes: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    parse_errors: Mapped[list | None] = mapped_column(
        JSONB,
        nullable=True,
    )
    content_hash: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    parsed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "audit_id", "page_id", name="ix_parsed_page_facts_audit_page"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<ParsedPageFact "
            f"id={self.id} "
            f"audit_id={self.audit_id} "
            f"page_id={self.page_id} "
            f"url={self.url!r}"
            f">"
        )
