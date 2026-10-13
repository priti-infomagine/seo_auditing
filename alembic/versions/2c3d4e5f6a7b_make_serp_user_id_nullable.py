"""Make SERP rank check user_id nullable for public endpoints

Revision ID: 2c3d4e5f6a7b
Revises: 1a2b3c4d5e6f
Create Date: 2026-10-13 11:47:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2c3d4e5f6a7b"
down_revision: Union[str, Sequence[str], None] = "1a2b3c4d5e6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The placeholder UUID used in the COALESCE expression so that
# anonymous (NULL user_id) checks are still de-duplicated by fingerprint.
ANONYMOUS_UUID = "00000000-0000-0000-0000-000000000000"


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("rank_checks")}
        if "user_id" in cols and not cols.get("user_id_nullable", False):
            # Make user_id nullable so anonymous (public) API callers
            # can create rank checks without a user account.
            op.alter_column("rank_checks", "user_id", nullable=True)

        # Replace the partial unique index so it de-duplicates NULL
        # user_id values (anonymous checks) via COALESCE.
        indexes = inspector.get_indexes("rank_checks")
        index_names = {idx["name"] for idx in indexes}
        if "uq_rank_checks_inflight" in index_names:
            op.drop_index(
                "uq_rank_checks_inflight",
                table_name="rank_checks",
                postgresql_where=sa.text(
                    "status IN ('queued','running')"
                ),
            )
        op.create_index(
            "uq_rank_checks_inflight",
            "rank_checks",
            [
                sa.text(f"COALESCE(user_id, '{ANONYMOUS_UUID}'::uuid)"),
                "fingerprint",
            ],
            unique=True,
            postgresql_where=sa.text("status IN ('queued','running')"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "rank_checks" in inspector.get_table_names():
        col_info = {
            c["name"]: c
            for c in inspector.get_columns("rank_checks")
        }
        if "user_id" in col_info:
            op.alter_column("rank_checks", "user_id", nullable=False)

        indexes = inspector.get_indexes("rank_checks")
        index_names = {idx["name"] for idx in indexes}
        if "uq_rank_checks_inflight" in index_names:
            op.drop_index(
                "uq_rank_checks_inflight",
                table_name="rank_checks",
                postgresql_where=sa.text(
                    "status IN ('queued','running')"
                ),
            )
        op.create_index(
            "uq_rank_checks_inflight",
            "rank_checks",
            ["user_id", "fingerprint"],
            unique=True,
            postgresql_where=sa.text("status IN ('queued','running')"),
        )
