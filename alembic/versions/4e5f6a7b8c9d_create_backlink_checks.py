"""create backlink checks

Revision ID: 4e5f6a7b8c9d
Revises: a2b3c4d5e6f7, 3d2c1f0d8e91
Create Date: 2026-10-06 15:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "4e5f6a7b8c9d"
down_revision: Union[str, Sequence[str], None] = (
    "a2b3c4d5e6f7",
    "3d2c1f0d8e91",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "backlink_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="processing"),
        sa.Column("evidence_limit", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backlink_checks_target_created",
        "backlink_checks",
        ["target", "created_at"],
    )
    op.create_index("ix_backlink_checks_status", "backlink_checks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_backlink_checks_status", table_name="backlink_checks")
    op.drop_index("ix_backlink_checks_target_created", table_name="backlink_checks")
    op.drop_table("backlink_checks")
