"""add structured Lighthouse recommendations

Revision ID: 06b2c3d4e5f6
Revises: 05a1b2c3d4e5
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "06b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "05a1b2c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lighthouse_page_results",
        sa.Column(
            "recommendations",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("lighthouse_page_results", "recommendations")