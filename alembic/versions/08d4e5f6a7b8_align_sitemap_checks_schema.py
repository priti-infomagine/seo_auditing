"""align sitemap checks schema with the current ORM model

Revision ID: 08d4e5f6a7b8
Revises: 07c3d4e5f6a7
Create Date: 2026-09-26
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "08d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "07c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "sitemap_checks" not in inspector.get_table_names():
        op.create_table(
            "sitemap_checks",
            sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("domain", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False, server_default="queued"),
            sa.Column("task_id", sa.String(length=255), nullable=True),
            sa.Column("progress", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("overall_status", sa.String(length=50), nullable=True),
            sa.Column("severity", sa.String(length=50), nullable=True),
            sa.Column("summary", postgresql.JSONB(), nullable=True),
            sa.Column("sitemaps", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("findings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("recommendations", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
            sa.Column("report_markdown", sa.Text(), nullable=True),
            sa.Column("cost_seconds", sa.Float(), nullable=True),
            sa.Column("check_version", sa.String(length=20), nullable=False, server_default="2.0.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f("sitemap_checks_pkey")),
        )
    else:
        existing = {column["name"] for column in inspector.get_columns("sitemap_checks")}
        columns = {
            "url": sa.Column("url", sa.Text(), nullable=True),
            "status": sa.Column("status", sa.String(length=50), nullable=True),
            "task_id": sa.Column("task_id", sa.String(length=255), nullable=True),
            "progress": sa.Column("progress", postgresql.JSONB(), nullable=True),
            "error": sa.Column("error", sa.Text(), nullable=True),
            "summary": sa.Column("summary", postgresql.JSONB(), nullable=True),
            "sitemaps": sa.Column("sitemaps", postgresql.JSONB(), nullable=True),
            "recommendations": sa.Column("recommendations", postgresql.JSONB(), nullable=True),
            "report_markdown": sa.Column("report_markdown", sa.Text(), nullable=True),
            "cost_seconds": sa.Column("cost_seconds", sa.Float(), nullable=True),
        }
        for name, column in columns.items():
            if name not in existing:
                op.add_column("sitemap_checks", column)

        op.execute(sa.text("UPDATE sitemap_checks SET url = COALESCE(url, '') WHERE url IS NULL"))
        op.execute(sa.text("UPDATE sitemap_checks SET status = COALESCE(status, 'queued') WHERE status IS NULL"))
        op.execute(sa.text("UPDATE sitemap_checks SET progress = COALESCE(progress, '{}'::jsonb) WHERE progress IS NULL"))
        op.execute(sa.text("UPDATE sitemap_checks SET sitemaps = COALESCE(sitemaps, '[]'::jsonb) WHERE sitemaps IS NULL"))
        op.execute(sa.text("UPDATE sitemap_checks SET findings = COALESCE(findings, '[]'::jsonb) WHERE findings IS NULL"))
        op.execute(sa.text("UPDATE sitemap_checks SET recommendations = COALESCE(recommendations, '[]'::jsonb) WHERE recommendations IS NULL"))

        for name in ("url", "status", "progress", "sitemaps", "findings", "recommendations"):
            op.alter_column("sitemap_checks", name, nullable=False)

    op.create_index(
        "ix_sitemap_checks_status",
        "sitemap_checks",
        ["status"],
        unique=False,
        if_not_exists=True,
    )
    op.create_index(
        "ix_sitemap_checks_domain_created",
        "sitemap_checks",
        ["domain", "created_at"],
        unique=False,
        if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_index("ix_sitemap_checks_domain_created", table_name="sitemap_checks", if_exists=True)
    op.drop_index("ix_sitemap_checks_status", table_name="sitemap_checks", if_exists=True)