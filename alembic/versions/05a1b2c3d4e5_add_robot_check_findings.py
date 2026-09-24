"""add detailed findings to robot checks

Revision ID: 05a1b2c3d4e5
Revises: 0485f3a2c1b7
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "05a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "0485f3a2c1b7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "robot_check",
        sa.Column(
            "findings",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("robot_check", "findings")