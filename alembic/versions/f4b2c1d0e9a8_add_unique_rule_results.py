"""add unique constraint on rule_evaluation_results (project_id, page_id, rule_id)

Revision ID: f4b2c1d0e9a8
Revises: e5f6a7b8c9d0
Create Date: 2026-08-25 00:00:00.000000

Backs the bulk upsert conflict target used by
RuleEvaluationResultRepository.bulk_upsert
(ON CONFLICT (project_id, page_id, rule_id) DO UPDATE).

NOTE: if a pre-existing database has duplicate (project_id, page_id, rule_id)
rows, this migration will fail. De-duplicate those rows before upgrading, e.g.:

    DELETE FROM rule_evaluation_results a
    USING rule_evaluation_results b
    WHERE a.id < b.id
      AND a.project_id = b.project_id
      AND a.page_id = b.page_id
      AND a.rule_id = b.rule_id;
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f4b2c1d0e9a8"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_rule_results_project_page_rule",
        "rule_evaluation_results",
        ["project_id", "page_id", "rule_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_rule_results_project_page_rule",
        "rule_evaluation_results",
        type_="unique",
    )
