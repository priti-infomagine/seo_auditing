"""transform subscriptions table: integer id -> UUID, add FK constraints

Revision ID: 64acf8cf44e5
Revises: eeb898d24f83
Create Date: 2026-09-16 16:53:49.119895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64acf8cf44e5'
down_revision: Union[str, Sequence[str], None] = 'eeb898d24f83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Transform subscriptions table from SERIAL to UUID with proper FKs."""
    # The subscriptions table was previously created by Base.metadata.create_all()
    # at runtime (no Alembic migration existed). It has an INTEGER SERIAL id
    # and no FK constraints to plans/users. Drop and recreate with the correct
    # schema to match the Subscription model.
    op.drop_table('subscriptions')

    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("plan_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("start_date", sa.DateTime(), nullable=False),
        sa.Column("current_period_start", sa.DateTime(), nullable=False),
        sa.Column("current_period_end", sa.DateTime(), nullable=False),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["plan_id"], ["plans.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    # Indexes for efficient lookups (use SQLAlchemy 'ix_' naming convention)
    op.create_index("ix_subscriptions_plan_id", "subscriptions", ["plan_id"])
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])


def downgrade() -> None:
    """Revert to the pre-migration subscriptions table (no FK constraints)."""
    op.drop_index("ix_subscriptions_user_id", table_name="subscriptions")
    op.drop_index("ix_subscriptions_plan_id", table_name="subscriptions")

    op.drop_table('subscriptions')

    # Recreate the original table as it would have been created by
    # Base.metadata.create_all() — Integer SERIAL id, no FK constraints.
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plan_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("user_id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("'active'"),
        ),
        sa.Column("start_date", sa.DateTime(), autoincrement=False, nullable=False),
        sa.Column("current_period_start", sa.DateTime(), autoincrement=False, nullable=False),
        sa.Column("current_period_end", sa.DateTime(), autoincrement=False, nullable=False),
        sa.Column(
            "cancel_at_period_end",
            sa.Boolean(),
            autoincrement=False,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("cancelled_at", sa.DateTime(), autoincrement=False, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_subscriptions_id", "subscriptions", ["id"], unique=False)
