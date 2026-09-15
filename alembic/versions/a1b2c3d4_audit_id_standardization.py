"""audit_id standardization — collapse audit_id/audit_id into single audit_id

Revision ID: a1b2c3d4
Revises: 2bc9883146d0
Create Date: 2026-09-11 07:05:00.000000

Eliminates ``audit_id`` as a separate concept.  ``audit_id`` is renamed to
``audit_id`` on the three analysis tables and becomes the single identifier.
``audit_id`` column is dropped from all four tables.

This is a pure schema rename + column drop — no data transformation needed
because audit_id already holds the value that audit_id must take.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "2bc9883146d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. seo_analysis_runs: audit_id → audit_id, drop audit_id ───────────
    op.execute("ALTER TABLE seo_analysis_runs RENAME COLUMN audit_id TO audit_id")
    op.drop_index("ix_seo_analysis_runs_audit_id", table_name="seo_analysis_runs", if_exists=True)
    op.drop_column("seo_analysis_runs", "audit_id")
    op.create_index(
        "ix_seo_analysis_runs_audit_id",
        "seo_analysis_runs",
        ["audit_id"],
        unique=True,
    )

    # ── 2. parsed_page_facts: audit_id → audit_id, drop audit_id ───────────
    op.execute("ALTER TABLE parsed_page_facts RENAME COLUMN audit_id TO audit_id")
    op.drop_index("ix_parsed_page_facts_project_crawl", table_name="parsed_page_facts", if_exists=True)
    try:
        op.drop_constraint("ix_parsed_page_facts_project_page", "parsed_page_facts", type_="unique")
    except Exception:
        pass
    op.drop_index("ix_parsed_page_facts_project_page", table_name="parsed_page_facts", if_exists=True)
    op.drop_column("parsed_page_facts", "audit_id")
    op.create_index(
        "ix_parsed_page_facts_audit_page",
        "parsed_page_facts",
        ["audit_id", "page_id"],
        unique=True,
    )

    # ── 3. rule_evaluation_results: audit_id → audit_id, drop audit_id ───
    op.execute("ALTER TABLE rule_evaluation_results RENAME COLUMN audit_id TO audit_id")
    op.drop_index("ix_rule_results_project_page_rule", table_name="rule_evaluation_results", if_exists=True)
    op.drop_index("ix_rule_results_project_page_ruleid", table_name="rule_evaluation_results", if_exists=True)
    try:
        op.drop_constraint(
            "uq_rule_results_project_page_rule",
            "rule_evaluation_results",
            type_="unique",
        )
    except Exception:
        pass
    op.drop_column("rule_evaluation_results", "audit_id")
    op.create_unique_constraint(
        "uq_rule_results_audit_page_rule",
        "rule_evaluation_results",
        ["audit_id", "page_id", "rule_id"],
    )
    op.create_index(
        "ix_rule_results_audit_page_rule",
        "rule_evaluation_results",
        ["audit_id", "page_id"],
        unique=False,
    )
    op.create_index(
        "ix_rule_results_audit_ruleid",
        "rule_evaluation_results",
        ["audit_id", "rule_id"],
        unique=False,
    )

    # ── 4. crawl_jobs: drop audit_id ─────────────────────────────────────
    op.drop_column("crawl_jobs", "audit_id")


def downgrade() -> None:
    # ── 4. crawl_jobs: re-add audit_id ───────────────────────────────────
    op.add_column("crawl_jobs", sa.Column("audit_id", sa.UUID(), nullable=True))

    # ── 3. rule_evaluation_results: audit_id → audit_id, re-add audit_id ─
    op.drop_index("ix_rule_results_audit_ruleid", table_name="rule_evaluation_results")
    op.drop_index("ix_rule_results_audit_page_rule", table_name="rule_evaluation_results")
    op.drop_constraint(
        "uq_rule_results_audit_page_rule",
        "rule_evaluation_results",
        type_="unique",
    )
    op.add_column("rule_evaluation_results", sa.Column("audit_id", sa.UUID(), nullable=False))
    op.execute("ALTER TABLE rule_evaluation_results RENAME COLUMN audit_id TO audit_id")
    op.create_unique_constraint(
        "uq_rule_results_project_page_rule",
        "rule_evaluation_results",
        ["audit_id", "page_id", "rule_id"],
    )
    op.create_index(
        "ix_rule_results_project_page_rule",
        "rule_evaluation_results",
        ["audit_id", "page_id"],
        unique=False,
    )
    op.create_index(
        "ix_rule_results_project_page_ruleid",
        "rule_evaluation_results",
        ["audit_id", "rule_id"],
        unique=False,
    )

    # ── 2. parsed_page_facts: audit_id → audit_id, re-add audit_id ────────
    op.drop_index("ix_parsed_page_facts_audit_page", table_name="parsed_page_facts")
    op.add_column("parsed_page_facts", sa.Column("audit_id", sa.UUID(), nullable=False))
    op.execute("ALTER TABLE parsed_page_facts RENAME COLUMN audit_id TO audit_id")
    op.create_index(
        "ix_parsed_page_facts_project_page",
        "parsed_page_facts",
        ["audit_id", "page_id"],
        unique=True,
    )
    op.create_index(
        "ix_parsed_page_facts_project_crawl",
        "parsed_page_facts",
        ["audit_id", "audit_id"],
        unique=False,
    )

    # ── 1. seo_analysis_runs: audit_id → audit_id, re-add audit_id ────────
    op.drop_index("ix_seo_analysis_runs_audit_id", table_name="seo_analysis_runs")
    op.add_column("seo_analysis_runs", sa.Column("audit_id", sa.UUID(), nullable=False))
    op.execute("ALTER TABLE seo_analysis_runs RENAME COLUMN audit_id TO audit_id")
    op.create_index(
        "ix_seo_analysis_runs_audit_id",
        "seo_analysis_runs",
        ["audit_id"],
        unique=True,
    )
