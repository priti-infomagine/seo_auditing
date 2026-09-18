"""create plans table

Revision ID: eeb898d24f83
Revises: c65858aed041
Create Date: 2026-09-15 17:12:29.689874

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eeb898d24f83'
down_revision: Union[str, Sequence[str], None] = 'c65858aed041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade():
    op.create_table(
        "plans",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),

        sa.Column("plan_type", sa.String(30), nullable=False),
        sa.Column("billing_interval", sa.String(20), nullable=True),

        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),

        sa.Column("audit_limit", sa.Integer(), nullable=True),
        sa.Column("fair_usage_enabled", sa.Boolean(), nullable=False),

        sa.Column("report_type", sa.String(30), nullable=True),

        sa.Column("is_active", sa.Boolean(), nullable=False),

        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),

        sa.UniqueConstraint("code"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    pass
