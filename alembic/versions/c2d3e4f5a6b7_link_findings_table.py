"""Create link_findings table and align link_analysis_checks schema

Revision ID: c2d3e4f5a6b7
Revises: a1b2c3d4e5f6

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing = {c["name"] for c in inspector.get_columns("link_analysis_checks")} if "link_analysis_checks" in inspector.get_table_names() else set()

    # --- Drop removed JSONB columns from link_analysis_checks ---
    for col in ("internal_links", "external_links", "broken_links", "orphan_pages", "redirects", "findings", "recommendations", "report_markdown"):
        if col in existing:
            op.drop_column("link_analysis_checks", col)

    # --- Add new columns ---
    if "pages_crawled" not in existing:
        op.add_column("link_analysis_checks", sa.Column("pages_crawled", sa.Integer(), nullable=True))
    if "crawl_truncated" not in existing:
        op.add_column("link_analysis_checks", sa.Column("crawl_truncated", sa.Boolean(), nullable=False, server_default="false"))

    # --- Create enum types (matching create_type=False in model.py) ---
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE link_analysis_overall_status AS ENUM ('pass', 'warning', 'fail', 'not_applicable'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "CREATE TYPE link_analysis_severity AS ENUM ('none', 'low', 'medium', 'high', 'critical'); "
        "EXCEPTION WHEN duplicate_object THEN NULL; "
        "END $$;"
    )

    # Add enum columns
    if "overall_status" not in existing:
        op.add_column(
            "link_analysis_checks",
            sa.Column(
                "overall_status",
                sa.Enum(
                    "pass", "warning", "fail", "not_applicable",
                    name="link_analysis_overall_status",
                    create_type=False,
                    validate_strings=True,
                ),
                nullable=True,
            ),
        )
    if "severity" not in existing:
        op.add_column(
            "link_analysis_checks",
            sa.Column(
                "severity",
                sa.Enum(
                    "none", "low", "medium", "high", "critical",
                    name="link_analysis_severity",
                    create_type=False,
                    validate_strings=True,
                ),
                nullable=True,
            ),
        )

    # --- Create link_findings table (if not exists) ---
    if "link_findings" not in inspector.get_table_names():
        op.create_table(
            "link_findings",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "check_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("link_analysis_checks.id", ondelete="CASCADE"),
                nullable=False,
                index=True,
            ),
            sa.Column("category", sa.String(length=20), nullable=False, server_default="standard"),
            sa.Column("type", sa.String(length=50), nullable=False),
            sa.Column(
                "severity",
                sa.Enum(
                    "none", "low", "medium", "high", "critical",
                    name="link_analysis_severity",
                    create_type=False,
                    validate_strings=True,
                ),
                nullable=False,
                server_default="low",
            ),
            sa.Column("target_url", sa.Text(), nullable=False, index=True),
            sa.Column("status_code", sa.SmallInteger(), nullable=True),
            sa.Column("final_url", sa.Text(), nullable=True),
            sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
            sa.Column("recommendation", postgresql.JSONB(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
        )
        op.create_index("ix_link_findings_check_category_type", "link_findings", ["check_id", "category", "type"])
        op.create_index("ix_link_findings_target", "link_findings", ["target_url"])
        op.create_index("ix_link_findings_severity", "link_findings", ["severity"])


def downgrade() -> None:
    op.drop_index("ix_link_findings_severity", table_name="link_findings", if_exists=True)
    op.drop_index("ix_link_findings_target", table_name="link_findings", if_exists=True)
    op.drop_index("ix_link_findings_check_category_type", table_name="link_findings", if_exists=True)
    op.drop_table("link_findings")

    op.drop_column("link_analysis_checks", "severity")
    op.drop_column("link_analysis_checks", "overall_status")
    op.drop_column("link_analysis_checks", "crawl_truncated")
    op.drop_column("link_analysis_checks", "pages_crawled")

    op.add_column("link_analysis_checks", sa.Column("redirects", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("link_analysis_checks", sa.Column("orphan_pages", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("link_analysis_checks", sa.Column("broken_links", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("link_analysis_checks", sa.Column("external_links", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("link_analysis_checks", sa.Column("internal_links", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("link_analysis_checks", sa.Column("progress", postgresql.JSONB(), nullable=False, server_default="{}"))

    op.execute("DROP TYPE IF EXISTS link_analysis_severity;")
    op.execute("DROP TYPE IF EXISTS link_analysis_overall_status;")
