"""Drop preview columns from rank_checks

Revision ID: b8c9d0e1f2a3
Revises: a771ee43e98c
Create Date: 2026-10-23 10:53:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, Sequence[str], None] = "a771ee43e98c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        inspector = sa.inspect(op.get_bind())
        cols = {c["name"] for c in inspector.get_columns("rank_checks")}
        to_drop = [
            c for c in cols
            if c in ("include_preview", "preview_status", "preview_html_url", "preview_image_url")
        ]
        for col in to_drop:
            op.drop_column("rank_checks", col)
    else:
        for col in ("include_preview", "preview_status", "preview_html_url", "preview_image_url"):
            op.drop_column("rank_checks", col)


def downgrade() -> None:
    op.add_column(
        "rank_checks",
        sa.Column("include_preview", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "rank_checks",
        sa.Column("preview_status", sa.Text(), nullable=False, server_default="none"),
    )
    op.add_column(
        "rank_checks",
        sa.Column("preview_html_url", sa.Text(), nullable=True),
    )
    op.add_column(
        "rank_checks",
        sa.Column("preview_image_url", sa.Text(), nullable=True),
    )
