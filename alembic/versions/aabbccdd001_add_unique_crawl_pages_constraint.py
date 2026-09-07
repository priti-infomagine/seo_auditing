"""Add unique constraint on crawl_pages(crawl_id, normalized_url)

Revision ID: aabbccdd001
Revises: a046fe9654e8
Create Date: 2026-09-04
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "aabbccdd001"
down_revision: Union[str, Sequence[str], None] = "a046fe9654e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_crawl_pages_crawl_id_normalized_url",
        "crawl_pages",
        ["crawl_id", "normalized_url"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_crawl_pages_crawl_id_normalized_url",
        "crawl_pages",
        type_="unique",
    )
