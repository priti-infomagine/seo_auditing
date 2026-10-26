"""SERP deep-tracking support: nullable domain + deep_tracking column + depth cap at 100

Revision ID: 4d5e6f7a8b9c
Revises: b8c9d0e1f2a3
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4d5e6f7a8b9c"
down_revision: Union[str, Sequence[str], None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("rank_checks")}

    # ── 1. Add deep_tracking column ────────────────────────────
    if "deep_tracking" not in cols:
        op.add_column(
            "rank_checks",
            sa.Column(
                "deep_tracking",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        op.alter_column(
            "rank_checks",
            "deep_tracking",
            server_default=None,
        )

    # ── 2. Make domain nullable ────────────────────────────────
    if "domain" in cols:
        domain_col = next(
            c for c in inspector.get_columns("rank_checks") if c["name"] == "domain"
        )
        if domain_col["nullable"]:
            # already nullable — nothing to do
            pass
        else:
            op.alter_column("rank_checks", "domain", nullable=True)

    # ── 3. Update depth check constraint (<= 100) ─────────────
    check_constraints = inspector.get_check_constraints("rank_checks")
    if any(cc["name"] == "ck_rank_checks_depth" for cc in check_constraints):
        op.drop_constraint(
            "ck_rank_checks_depth", "rank_checks", type_="check"
        )
    op.create_check_constraint(
        "ck_rank_checks_depth",
        "rank_checks",
        sa.text("depth >= 10 AND depth <= 100"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("rank_checks")}

    # ── 1. Restore depth check constraint (<= 200) ──────────
    check_constraints = inspector.get_check_constraints("rank_checks")
    if any(cc["name"] == "ck_rank_checks_depth" for cc in check_constraints):
        op.drop_constraint(
            "ck_rank_checks_depth", "rank_checks", type_="check"
        )
    op.create_check_constraint(
        "ck_rank_checks_depth",
        "rank_checks",
        sa.text("depth >= 10 AND depth <= 200"),
    )

    # ── 2. Make domain non-nullable ───────────────────────────
    if "domain" in cols:
        op.alter_column("rank_checks", "domain", nullable=False)

    # ── 3. Drop deep_tracking column ──────────────────────────
    if "deep_tracking" in cols:
        op.drop_column("rank_checks", "deep_tracking")
