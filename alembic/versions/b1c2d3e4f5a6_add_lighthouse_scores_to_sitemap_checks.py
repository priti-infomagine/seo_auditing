"""add accessibility_score and best_practices_score to sitemap_checks

Revision ID: b1c2d3e4f5a6
Revises: 3807b3c21605
Create Date: 2026-09-28

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "3807b3c21605"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing = {c["name"] for c in inspector.get_columns("sitemap_checks")} if "sitemap_checks" in inspector.get_table_names() else set()

    if "accessibility_score" not in existing:
        op.add_column("sitemap_checks", sa.Column("accessibility_score", sa.Integer(), nullable=True))
    if "best_practices_score" not in existing:
        op.add_column("sitemap_checks", sa.Column("best_practices_score", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "sitemap_checks" in inspector.get_table_names():
        existing = {c["name"] for c in inspector.get_columns("sitemap_checks")}
        if "best_practices_score" in existing:
            op.drop_column("sitemap_checks", "best_practices_score")
        if "accessibility_score" in existing:
            op.drop_column("sitemap_checks", "accessibility_score")
