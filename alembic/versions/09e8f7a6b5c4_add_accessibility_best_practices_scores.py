"""Add accessibility_score and best_practices_score to lighthouse_page_results

Revision ID: 09e8f7a6b5c4
Revises: 08d4e5f6a7b8
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "09e8f7a6b5c4"
down_revision: Union[str, Sequence[str], None] = "08d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "lighthouse_page_results" in inspector.get_table_names():
        existing = {column["name"] for column in inspector.get_columns("lighthouse_page_results")}
        if "accessibility_score" not in existing:
            op.add_column(
                "lighthouse_page_results",
                sa.Column("accessibility_score", sa.Integer(), nullable=True),
            )
        if "best_practices_score" not in existing:
            op.add_column(
                "lighthouse_page_results",
                sa.Column("best_practices_score", sa.Integer(), nullable=True),
            )


def downgrade() -> None:
    op.drop_column("lighthouse_page_results", "best_practices_score", if_exists=True)
    op.drop_column("lighthouse_page_results", "accessibility_score", if_exists=True)