"""create persisted sitemap checks

Revision ID: 07c3d4e5f6a7
Revises: 07515632cae3
Create Date: 2026-09-25

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "07c3d4e5f6a7"
down_revision: Union[str, Sequence[str], None] = "07515632cae3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_types = {row[0] for row in bind.execute(sa.text("SELECT typname FROM pg_type WHERE typname IN ('fetchstatus', 'overallstatus', 'severity')")).fetchall()}
    
    # Create enum types if they don't exist
    if "fetchstatus" not in existing_types:
        fetchstatus_enum = sa.Enum("SUCCESS", "NOT_FOUND", "UNREACHABLE", name="fetchstatus", create_type=True)
        fetchstatus_enum.create(bind, checkfirst=True)
    else:
        fetchstatus_enum = sa.Enum("SUCCESS", "NOT_FOUND", "UNREACHABLE", name="fetchstatus", create_type=False)
    
    if "overallstatus" not in existing_types:
        overallstatus_enum = sa.Enum("PASS", "WARNING", "FAIL", "NOT_APPLICABLE", name="overallstatus", create_type=True)
        overallstatus_enum.create(bind, checkfirst=True)
    else:
        overallstatus_enum = sa.Enum("PASS", "WARNING", "FAIL", "NOT_APPLICABLE", name="overallstatus", create_type=False)
    
    if "severity" not in existing_types:
        severity_enum = sa.Enum("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL", name="severity", create_type=True)
        severity_enum.create(bind, checkfirst=True)
    else:
        severity_enum = sa.Enum("NONE", "LOW", "MEDIUM", "HIGH", "CRITICAL", name="severity", create_type=False)

    op.create_table(
        "sitemap_checks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("robots_fetch_status", fetchstatus_enum, nullable=False),
        sa.Column("robots_status_code", sa.SmallInteger(), nullable=True),
        sa.Column("robots_final_url", sa.Text(), nullable=True),
        sa.Column("raw_robots_content", sa.Text(), nullable=True),
        sa.Column("sitemaps_declared", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("sitemap_results", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("findings", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("overall_status", overallstatus_enum, nullable=False),
        sa.Column("severity", severity_enum, nullable=False),
        sa.Column("check_version", sa.String(length=20), nullable=False, server_default="1.0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("sitemap_checks_pkey")),
    )
    op.create_index(
        "ix_sitemap_checks_domain_created",
        "sitemap_checks",
        ["domain", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_sitemap_checks_domain",
        "sitemap_checks",
        ["domain"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_sitemap_checks_domain", table_name="sitemap_checks")
    op.drop_index("ix_sitemap_checks_domain_created", table_name="sitemap_checks")
    op.drop_table("sitemap_checks")