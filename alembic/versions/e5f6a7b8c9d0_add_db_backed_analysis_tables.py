"""add_db_backed_analysis_tables

Revision ID: e5f6a7b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-08-17 13:55:00.000000

Add three new tables for the DB-backed end-to-end analysis pipeline:
  - parsed_page_facts  (project_id, page_id)
  - rule_evaluation_results (project_id, page_id, rule_id)
  - seo_analysis_runs  (project_id)

All use project_id as the main tracking key.
crawl_id is kept for join-back to existing crawler tables.

Indexes are limited to TWO columns per index.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. parsed_page_facts ──────────────────────────────────────────────
    op.create_table(
        "parsed_page_facts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("crawl_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("parsed_data", sa.JSON(), nullable=False),
        sa.Column("page_facts", sa.JSON(), nullable=False),
        sa.Column("elements", sa.JSON(), nullable=True),
        sa.Column("attributes", sa.JSON(), nullable=True),
        sa.Column("parse_errors", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=True),
        sa.Column("parsed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Two-column unique index
    op.create_index(
        "ix_parsed_page_facts_project_page",
        "parsed_page_facts",
        ["project_id", "page_id"],
        unique=True,
    )
    # Two-column non-unique index for crawl_id lookups
    op.create_index(
        "ix_parsed_page_facts_project_crawl",
        "parsed_page_facts",
        ["project_id", "crawl_id"],
        unique=False,
    )

    # ── 2. rule_evaluation_results ────────────────────────────────────────
    op.create_table(
        "rule_evaluation_results",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("crawl_id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("score_impact", sa.Float(), nullable=False, server_default="0"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("rule_data", sa.JSON(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Two-column unique index for dedup per rule per page
    op.create_index(
        "ix_rule_results_project_page_rule",
        "rule_evaluation_results",
        ["project_id", "page_id"],
        unique=False,
    )
    op.create_index(
        "ix_rule_results_project_page_ruleid",
        "rule_evaluation_results",
        ["project_id", "rule_id"],
        unique=False,
    )

    # ── 3. seo_analysis_runs ──────────────────────────────────────────────
    op.create_table(
        "seo_analysis_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("crawl_id", sa.UUID(), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("grade", sa.String(length=5), nullable=True),
        sa.Column("total_pages_scored", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_rules_evaluated", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("critical_issues", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_pages", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.JSON(), nullable=True),
        sa.Column("category_scores", sa.JSON(), nullable=True),
        sa.Column("top_issues", sa.JSON(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("output_file_path", sa.String(length=1024), nullable=True),
        sa.Column("analysis_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Two-column unique index for project_id (also serves as domain lookup via separate index)
    op.create_index(
        "ix_seo_analysis_runs_project_id",
        "seo_analysis_runs",
        ["project_id"],
        unique=True,
    )
    # Two-column index for domain + status lookups
    op.create_index(
        "ix_seo_analysis_runs_domain_status",
        "seo_analysis_runs",
        ["domain", "analysis_status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_seo_analysis_runs_domain_status", table_name="seo_analysis_runs")
    op.drop_index("ix_seo_analysis_runs_project_id", table_name="seo_analysis_runs")
    op.drop_table("seo_analysis_runs")

    op.drop_index("ix_rule_results_project_page_ruleid", table_name="rule_evaluation_results")
    op.drop_index("ix_rule_results_project_page_rule", table_name="rule_evaluation_results")
    op.drop_table("rule_evaluation_results")

    op.drop_index("ix_parsed_page_facts_project_crawl", table_name="parsed_page_facts")
    op.drop_index("ix_parsed_page_facts_project_page", table_name="parsed_page_facts")
    op.drop_table("parsed_page_facts")
