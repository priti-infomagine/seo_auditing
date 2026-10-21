"""Migrate rank_checks from location_code/language_code to location_name/language_name

Removes foreign-key dependencies on serp_locations / serp_languages.
Location and language are now stored as DataForSEO location_name /
language_name strings, which the API accepts directly.

Revision ID: 3d4e5f6a7b8c
Revises: 2c3d4e5f6a7b
Create Date: 2026-10-14 08:37:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3d4e5f6a7b8c"
down_revision: Union[str, Sequence[str], None] = "2c3d4e5f6a7b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" not in inspector.get_table_names():
        # Table doesn't exist yet (fresh DB) — no migration needed.
        return

    cols = {c["name"] for c in inspector.get_columns("rank_checks")}

    # ── 1. Add new string columns ────────────────────────────
    if "location_name" not in cols:
        op.add_column(
            "rank_checks",
            sa.Column("location_name", sa.Text(), nullable=True),
        )
    if "language_name" not in cols:
        op.add_column(
            "rank_checks",
            sa.Column("language_name", sa.Text(), nullable=True),
        )

    # ── 2. Backfill from old columns (if data exists) ────────
    if (
        "location_code" in cols
        and "location_name" in cols
    ):
        # Join rank_checks → serp_locations to get the name
        op.execute(
            sa.text(
                """
                UPDATE rank_checks rc
                SET location_name = sl.name
                FROM serp_locations sl
                WHERE rc.location_code = sl.location_code
                  AND rc.location_name IS NULL
                """
            )
        )

    if (
        "language_code" in cols
        and "language_name" in cols
    ):
        op.execute(
            sa.text(
                """
                UPDATE rank_checks rc
                SET language_name = sl.name
                FROM serp_languages sl
                WHERE rc.language_code = sl.language_code
                  AND rc.language_name IS NULL
                """
            )
        )

    # ── 3. Drop FK constraints ───────────────────────────────
    fks = inspector.get_foreign_keys("rank_checks")
    fk_names = {fk["name"] for fk in fks if fk.get("name")}

    for fk_name in list(fk_names):
        if "location_code" in fk_name.lower() or "language_code" in fk_name.lower():
            op.drop_constraint(fk_name, "rank_checks", type_="foreignkey")

    # ── 4. Drop old check constraint on depth ────────────────
    check_constraints = inspector.get_check_constraints("rank_checks")
    for cc in check_constraints:
        if cc["name"] == "ck_rank_checks_depth":
            op.drop_constraint("ck_rank_checks_depth", "rank_checks", type_="check")

    # ── 5. Add updated check constraint (allows 10-200) ─────
    op.create_check_constraint(
        "ck_rank_checks_depth",
        "rank_checks",
        sa.text("depth >= 10 AND depth <= 200"),
    )

    # ── 6. Drop old columns ─────────────────────────────────
    if "location_code" in cols:
        op.drop_column("rank_checks", "location_code")
    if "language_code" in cols:
        op.drop_column("rank_checks", "language_code")

    # ── 7. Make new columns non-nullable ─────────────────────
    if "location_name" in cols:
        op.alter_column("rank_checks", "location_name", nullable=False)
    if "language_name" in cols:
        op.alter_column("rank_checks", "language_name", nullable=False)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("rank_checks")}

    # ── 1. Re-add old columns ────────────────────────────────
    if "location_code" not in cols:
        op.add_column(
            "rank_checks",
            sa.Column("location_code", sa.Integer(), nullable=True),
        )
    if "language_code" not in cols:
        op.add_column(
            "rank_checks",
            sa.Column("language_code", sa.Text(), nullable=True),
        )

    # ── 2. Restore check constraint ──────────────────────────
    check_constraints = inspector.get_check_constraints("rank_checks")
    for cc in check_constraints:
        if cc["name"] == "ck_rank_checks_depth":
            op.drop_constraint("ck_rank_checks_depth", "rank_checks", type_="check")
    op.create_check_constraint(
        "ck_rank_checks_depth",
        "rank_checks",
        sa.text("depth IN (10,20,50,100)"),
    )

    # ── 3. Drop new columns ──────────────────────────────────
    if "location_name" in cols:
        op.drop_column("rank_checks", "location_name")
    if "language_name" in cols:
        op.drop_column("rank_checks", "language_name")
