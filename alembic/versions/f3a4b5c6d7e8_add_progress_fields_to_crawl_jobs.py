"""add progress fields to crawl_jobs

Revision ID: f3a4b5c6d7e8
Revises: e5f6a7b8c9d0
Create Date: 2026-08-18 14:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crawl_jobs", sa.Column("total_pages", sa.Integer(), nullable=True))
    op.add_column("crawl_jobs", sa.Column("current_page", sa.Integer(), nullable=True))
    op.add_column("crawl_jobs", sa.Column("progress_percent", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("crawl_jobs", "progress_percent")
    op.drop_column("crawl_jobs", "current_page")
    op.drop_column("crawl_jobs", "total_pages")
