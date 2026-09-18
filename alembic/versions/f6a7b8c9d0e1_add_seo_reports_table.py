"""add seo_reports table

Revision ID: f6a7b8c9d0e1
Revises: 6065450519c4
Create Date: 2026-09-15 07:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "6065450519c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "seo_reports",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("audit_id", sa.UUID(), nullable=False),
        sa.Column("report_version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("delivered_to", sa.ARRAY(sa.String(length=255)), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_seo_reports_audit_id", "seo_reports", ["audit_id"], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_seo_reports_audit_id", table_name="seo_reports")
    op.drop_table("seo_reports")
