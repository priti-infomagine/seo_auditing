"""Make overall_status and severity nullable in sitemap_checks

Revision ID: 0a1b2c3d4e5f
Revises: 09e8f7a6b5c4
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0a1b2c3d4e5f"
down_revision: Union[str, Sequence[str], None] = "09e8f7a6b5c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make overall_status and severity nullable since they're only set after check completes
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sitemap_checks" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("sitemap_checks")}
        if "overall_status" in cols:
            op.alter_column("sitemap_checks", "overall_status", nullable=True)
        if "severity" in cols:
            op.alter_column("sitemap_checks", "severity", nullable=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sitemap_checks" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("sitemap_checks")}
        if "overall_status" in cols:
            op.alter_column("sitemap_checks", "overall_status", nullable=False)
        if "severity" in cols:
            op.alter_column("sitemap_checks", "severity", nullable=False)