"""Create streaming audit tables.

Revision ID: 3d2c1f0d8e91
Revises: f7c282b13848
Create Date: 2026-10-06
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "3d2c1f0d8e91"
down_revision = "f7c282b13848"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "streaming_audit_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("seed_url", sa.String(length=2048), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_depth", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("concurrency", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("browser_concurrency", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("request_timeout", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("queued_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("final_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_info", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
    )
    op.create_index(op.f("ix_streaming_audit_runs_user_id"), "streaming_audit_runs", ["user_id"], unique=False)
    op.create_index(op.f("ix_streaming_audit_runs_domain"), "streaming_audit_runs", ["domain"], unique=False)

    op.create_table(
        "streaming_page_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_url", sa.String(length=2048), nullable=False),
        sa.Column("canonical_url", sa.String(length=2048), nullable=True),
        sa.Column("http_status", sa.Integer(), nullable=True),
        sa.Column("processing_status", sa.String(length=32), nullable=False, server_default="completed"),
        sa.Column("page_score", sa.Float(), nullable=True),
        sa.Column("processing_latency_ms", sa.Integer(), nullable=True),
        sa.Column("parsed_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("page_findings", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("discovered_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error_info", sa.Text(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.UniqueConstraint("audit_id", "normalized_url", name="uq_streaming_page_result_audit_url"),
    )
    op.create_index(op.f("ix_streaming_page_results_audit_id"), "streaming_page_results", ["audit_id"], unique=False)
    op.create_index(op.f("ix_streaming_page_results_normalized_url"), "streaming_page_results", ["normalized_url"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_streaming_page_results_normalized_url"), table_name="streaming_page_results")
    op.drop_index(op.f("ix_streaming_page_results_audit_id"), table_name="streaming_page_results")
    op.drop_table("streaming_page_results")
    op.drop_index(op.f("ix_streaming_audit_runs_domain"), table_name="streaming_audit_runs")
    op.drop_index(op.f("ix_streaming_audit_runs_user_id"), table_name="streaming_audit_runs")
    op.drop_table("streaming_audit_runs")
