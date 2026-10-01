"""store per-page link analysis evidence

Revision ID: d8e4b9a12f30
Revises: f7c282b13848
Create Date: 2026-09-30 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d8e4b9a12f30"
down_revision: Union[str, Sequence[str], None] = "f7c282b13848"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "link_analysis_pages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "check_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("link_analysis_checks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_url", sa.Text(), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False, server_default="-1"),
        sa.Column("inbound_internal_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outbound_internal_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("outbound_external_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broken_internal_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broken_external_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_orphan", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_dead_end", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("issues", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("internal_links", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("external_links", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("check_id", "page_url", name="uq_link_analysis_pages_check_url"),
    )
    op.create_index(
        "ix_link_analysis_pages_check_depth",
        "link_analysis_pages",
        ["check_id", "depth"],
    )


def downgrade() -> None:
    op.drop_index("ix_link_analysis_pages_check_depth", table_name="link_analysis_pages")
    op.drop_table("link_analysis_pages")