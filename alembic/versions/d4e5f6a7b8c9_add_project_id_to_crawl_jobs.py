"""add project_id to crawl_jobs

Revision ID: d4e5f6a7b8c9
Revises: 2bc9883146d0
Create Date: 2026-09-11 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = '2bc9883146d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "crawl_jobs",
        sa.Column(
            "project_id",
            sa.UUID(),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_crawl_jobs_project_id", table_name="crawl_jobs")
    op.drop_column("crawl_jobs", "project_id")
