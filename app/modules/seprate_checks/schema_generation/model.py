import enum
import uuid

from sqlalchemy import Enum, Float, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin


class SchemaType(str, enum.Enum):
    ORGANIZATION = "organization"
    LOCAL_BUSINESS = "local_business"
    ARTICLE = "article"
    PRODUCT = "product"


class ArticleSubType(str, enum.Enum):
    ARTICLE = "article"
    BLOG_POSTING = "blog_posting"
    NEWS_ARTICLE = "news_article"


class GenerationStatus(str, enum.Enum):
    COMPLETED = "completed"
    FAILED = "failed"


class SchemaGeneration(TimestampMixin, Base):
    __tablename__ = "schema_generations"

    __table_args__ = (
        Index("ix_schema_generations_type_created", "schema_type", "created_at"),
        Index("ix_schema_generations_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    schema_type: Mapped[str] = mapped_column(
        Enum(SchemaType, name="schematype", create_type=False, validate_strings=True),
        nullable=False,
        index=True,
    )
    article_subtype: Mapped[str | None] = mapped_column(
        Enum(ArticleSubType, name="articlesubtype", create_type=False, validate_strings=True),
        nullable=True,
    )
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    generated_jsonld: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(GenerationStatus, name="generationstatus", create_type=False, validate_strings=True),
        nullable=False,
        default=GenerationStatus.COMPLETED.value,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0.0"
    )


class SchemaAudit(TimestampMixin, Base):
    __tablename__ = "schema_audits"

    __table_args__ = (
        Index("ix_schema_audits_url_created", "url", "created_at"),
        Index("ix_schema_audits_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    detected_schemas: Mapped[list[dict]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    check_version: Mapped[str] = mapped_column(
        String(20), nullable=False, default="1.0.0"
    )