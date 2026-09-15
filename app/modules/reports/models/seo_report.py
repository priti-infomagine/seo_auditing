"""
SEO Report model.

Tracks generated PDF reports for each audit: which audit_id it was generated
for, the report version, the list of email addresses it was delivered to,
and when it was created / updated / delivered.
"""
import uuid
from datetime import datetime

from sqlalchemy import Integer, String, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class SeoReport(TimestampMixin, Base):
    """One row per generated report PDF tied to an audit_id."""

    __tablename__ = "seo_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    audit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        unique=True,
        index=True,
    )
    report_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )
    delivered_to: Mapped[list[str]] = mapped_column(
        ARRAY(String(255)),
        nullable=False,
        server_default=text("'{}'"),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        "delivered_at",
        nullable=True,
    )

    def __repr__(self) -> str:
        return (
            f"<SeoReport "
            f"id={self.id} "
            f"audit_id={self.audit_id} "
            f"version={self.report_version} "
            f"delivered_to={self.delivered_to}"
            f">"
        )