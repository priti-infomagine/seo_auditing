"""Add location_code to rank_checks for exact location targeting

Revision ID: f8a9b0c1d2e3
Revises: e5f6a7b8c9d0
Create Date: 2026-10-28 10:28:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" not in inspector.get_table_names():
        # Table doesn't exist yet (fresh DB) — created by the model.
        return

    cols = {c["name"] for c in inspector.get_columns("rank_checks")}

    # ── Add nullable location_code column ──────────────────────
    # Nullable so existing rows (created before code-based targeting)
    # and backward-compatible, name-only requests remain valid.
    if "location_code" not in cols:
        op.add_column(
            "rank_checks",
            sa.Column(
                "location_code",
                sa.Integer(),
                nullable=True,
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("rank_checks")}

    if "location_code" in cols:
        op.drop_column("rank_checks", "location_code")
