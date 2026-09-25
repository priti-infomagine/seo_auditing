"""create persisted sitemap checks

Revision ID: 07c3d4e5f6a7
Revises: 07515632cae3
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "07c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "07515632cae3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sitemap_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("sitemap_checks_pkey")),
    )
    op.create_index(
        "ix_sitemap_checks_url_created",
        "sitemap_checks",
        ["url", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sitemap_checks_url_created", table_name="sitemap_checks")
    op.drop_table("sitemap_checks")