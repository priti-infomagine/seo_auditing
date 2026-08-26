"""add parsed_data to page_snapshots

Revision ID: f5a6b7c8d9e0
Revises: f4b2c1d0e9a8
Create Date: 2026-08-26

Adds a nullable ``parsed_data`` JSONB column to ``page_snapshots`` so that
the ParsedPage result from the crawl stage can be persisted alongside the
HTML snapshot.  This eliminates the duplicate parse performed later in
``DBParserService.parse_page``.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "f4b2c1d0e9a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "page_snapshots",
        sa.Column("parsed_data", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("page_snapshots", "parsed_data")
