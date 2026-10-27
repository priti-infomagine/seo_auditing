"""Set deep_tracking column default to true

Revision ID: e5f6a7b8c9d0
Revises: 4d5e6f7a8b9c
Create Date: 2026-10-27 06:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "4d5e6f7a8b9c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("rank_checks")}

    if "deep_tracking" in cols:
        op.alter_column(
            "rank_checks",
            "deep_tracking",
            server_default=sa.text("true"),
        )


def downgrade() -> None:
    op.alter_column(
        "rank_checks",
        "deep_tracking",
        server_default=sa.text("false"),
    )
