from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgreSQLUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RedirectUrlAudit(Base):
    __tablename__ = "redirect_url_audits"

    id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True), primary_key=True
    )
    domain: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    max_urls: Mapped[int] = mapped_column(Integer, nullable=False)
    max_depth: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    max_hops: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    discovered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    discovery_errors: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    summary: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    cost_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    error_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(),
        nullable=False,
    )


class RedirectUrlNode(Base):
    __tablename__ = "redirect_url_nodes"
    __table_args__ = (
        UniqueConstraint(
            "audit_id",
            "normalized_url_hash",
            name="uq_redirect_node_url_hash",
        ),
        Index("ix_redirect_url_nodes_audit_order", "audit_id", "discovery_order"),
        Index("ix_redirect_url_nodes_audit_status", "audit_id", "status_code"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    audit_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("redirect_url_audits.id", ondelete="CASCADE"),
        nullable=False,
    )
    url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_url_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    discovery_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    crawl_depth: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    redirect_hops: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="unverified")
    error_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_redirect: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_internal_redirect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_external_redirect: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    is_broken: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    in_sitemap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class RedirectUrlEdge(Base):
    __tablename__ = "redirect_url_edges"
    __table_args__ = (
        UniqueConstraint(
            "audit_id",
            "source_node_id",
            "edge_type",
            "position",
            name="uq_redirect_edge_position",
        ),
        Index("ix_redirect_url_edges_audit", "audit_id"),
        Index("ix_redirect_url_edges_target", "audit_id", "target_node_id"),
    )

    id: Mapped[UUID] = mapped_column(PostgreSQLUUID(as_uuid=True), primary_key=True)
    audit_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("redirect_url_audits.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_node_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("redirect_url_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[UUID] = mapped_column(
        PostgreSQLUUID(as_uuid=True),
        ForeignKey("redirect_url_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type: Mapped[str] = mapped_column(String(16), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    hop_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
