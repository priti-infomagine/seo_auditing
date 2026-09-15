import uuid

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class ParsedPageFact(TimestampMixin, Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    code : Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  
    Description: Mapped[str] = mapped_column(Text, nullable=True)
    plan_type: Mapped[str] = mapped_column(String(50), nullable=False)
    price: Mapped[float] = mapped_column(nullable=False)        
    audit_limits: Mapped[int] = mapped_column(nullable=False)
    report_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)
