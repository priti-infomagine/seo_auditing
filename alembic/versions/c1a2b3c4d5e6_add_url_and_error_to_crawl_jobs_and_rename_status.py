"""add_url_and_error_to_crawl_jobs_and_rename_status

Revision ID: c1a2b3c4d5e6
Revises: b2393caacd1c
Create Date: 2026-08-08 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "b2393caacd1c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("crawl_jobs", sa.Column("url", sa.String(length=2048), nullable=False))
    op.add_column("crawl_jobs", sa.Column("error", sa.String(length=1024), nullable=True))

    op.execute("CREATE TYPE crawl_job_status_enum_v2 AS ENUM ('queued', 'crawling', 'completed', 'failed', 'cancelled')")

    op.execute(
        "ALTER TABLE crawl_jobs "
        "ALTER COLUMN status TYPE crawl_job_status_enum_v2 "
        "USING CASE status "
        "WHEN 'pending' THEN 'queued'::crawl_job_status_enum_v2 "
        "WHEN 'running' THEN 'crawling'::crawl_job_status_enum_v2 "
        "WHEN 'completed' THEN 'completed'::crawl_job_status_enum_v2 "
        "WHEN 'failed' THEN 'failed'::crawl_job_status_enum_v2 "
        "ELSE 'queued'::crawl_job_status_enum_v2 "
        "END"
    )

    op.execute("DROP TYPE crawl_job_status_enum")
    op.execute("ALTER TYPE crawl_job_status_enum_v2 RENAME TO crawl_job_status_enum")


def downgrade() -> None:
    op.drop_column("crawl_jobs", "error")
    op.drop_column("crawl_jobs", "url")

    op.execute("CREATE TYPE crawl_job_status_enum_v1 AS ENUM ('pending', 'running', 'completed', 'failed')")

    op.execute(
        "ALTER TABLE crawl_jobs "
        "ALTER COLUMN status TYPE crawl_job_status_enum_v1 "
        "USING CASE status "
        "WHEN 'queued' THEN 'pending'::crawl_job_status_enum_v1 "
        "WHEN 'crawling' THEN 'running'::crawl_job_status_enum_v1 "
        "WHEN 'completed' THEN 'completed'::crawl_job_status_enum_v1 "
        "WHEN 'failed' THEN 'failed'::crawl_job_status_enum_v1 "
        "WHEN 'cancelled' THEN 'pending'::crawl_job_status_enum_v1 "
        "ELSE 'pending'::crawl_job_status_enum_v1 "
        "END"
    )

    op.execute("DROP TYPE crawl_job_status_enum")
    op.execute("ALTER TYPE crawl_job_status_enum_v1 RENAME TO crawl_job_status_enum")
