"""create standalone metadata checks

Revision ID: a2b3c4d5e6f7
Revises: d8e4b9a12f30
Create Date: 2026-10-01 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "d8e4b9a12f30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "meta_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("task_id", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("progress", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("max_pages", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_depth", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("pages", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("summary", postgresql.JSONB(), nullable=True),
        sa.Column("findings", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("overall_status", sa.String(length=20), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=True),
        sa.Column("cost_seconds", sa.Float(), nullable=True),
        sa.Column("check_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_meta_checks_domain", "meta_checks", ["domain"])
    op.create_index("ix_meta_checks_domain_created", "meta_checks", ["domain", "created_at"])
    op.create_index("ix_meta_checks_status", "meta_checks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_meta_checks_status", table_name="meta_checks")
    op.drop_index("ix_meta_checks_domain_created", table_name="meta_checks")
    op.drop_index("ix_meta_checks_domain", table_name="meta_checks")
    op.drop_table("meta_checks")