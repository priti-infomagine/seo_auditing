"""persist redirect audit nodes and edges

Revision ID: f2a8c7d1e609
Revises: e18b2c7d9a41
Create Date: 2026-10-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f2a8c7d1e609"
down_revision: Union[str, Sequence[str], None] = "e18b2c7d9a41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "redirect_url_audits",
        sa.Column("max_depth", sa.Integer(), server_default="5", nullable=False),
        if_not_exists=True,
    )
    op.add_column(
        "redirect_url_audits",
        sa.Column("max_hops", sa.Integer(), server_default="10", nullable=False),
        if_not_exists=True,
    )
    op.add_column(
        "redirect_url_audits",
        sa.Column(
            "discovery_errors",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        if_not_exists=True,
    )
    op.add_column(
        "redirect_url_audits",
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        if_not_exists=True,
    )
    op.add_column(
        "redirect_url_audits",
        sa.Column("cost_seconds", sa.Float(), nullable=True),
        if_not_exists=True,
    )
    op.add_column(
        "redirect_url_audits",
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        if_not_exists=True,
    )

    op.create_table(
        "redirect_url_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("normalized_url", sa.Text(), nullable=False),
        sa.Column("normalized_url_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("discovery_order", sa.Integer(), nullable=True),
        sa.Column("crawl_depth", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("final_url", sa.Text(), nullable=True),
        sa.Column("redirect_hops", sa.Integer(), server_default="0", nullable=False),
        sa.Column("state", sa.String(length=32), server_default="unverified", nullable=False),
        sa.Column("error_type", sa.String(length=64), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("is_redirect", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column(
            "is_internal_redirect",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column(
            "is_external_redirect",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
        sa.Column("is_broken", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("in_sitemap", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.ForeignKeyConstraint(
            ["audit_id"], ["redirect_url_audits.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "audit_id",
            "normalized_url_hash",
            name="uq_redirect_node_url_hash",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "ix_redirect_url_nodes_audit_order",
        "redirect_url_nodes",
        ["audit_id", "discovery_order"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_redirect_url_nodes_audit_status",
        "redirect_url_nodes",
        ["audit_id", "status_code"],
        if_not_exists=True,
    )

    op.create_table(
        "redirect_url_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("audit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("edge_type", sa.String(length=16), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("hop_number", sa.Integer(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["audit_id"], ["redirect_url_audits.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_node_id"], ["redirect_url_nodes.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["target_node_id"], ["redirect_url_nodes.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "audit_id",
            "source_node_id",
            "edge_type",
            "position",
            name="uq_redirect_edge_position",
        ),
        if_not_exists=True,
    )
    op.create_index(
        "ix_redirect_url_edges_audit",
        "redirect_url_edges",
        ["audit_id"],
        if_not_exists=True,
    )
    op.create_index(
        "ix_redirect_url_edges_target",
        "redirect_url_edges",
        ["audit_id", "target_node_id"],
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table("redirect_url_edges", if_exists=True)
    op.drop_table("redirect_url_nodes", if_exists=True)
    for column_name in (
        "checked_at",
        "cost_seconds",
        "summary",
        "discovery_errors",
        "max_hops",
        "max_depth",
    ):
        op.drop_column("redirect_url_audits", column_name, if_exists=True)
