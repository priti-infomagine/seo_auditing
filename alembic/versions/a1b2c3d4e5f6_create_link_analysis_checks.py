"""create link_analysis_checks table

Revision ID: a1b2c3d4e5f6
Revises: 3807b3c21605
Create Date: 2026-09-28 11:03:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '3807b3c21605'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'link_analysis_checks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('domain', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='queued'),
        sa.Column('task_id', sa.String(length=255), nullable=True),
        sa.Column('progress', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('summary', postgresql.JSONB(), nullable=True),
        sa.Column('internal_links', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('external_links', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('broken_links', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('orphan_pages', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('redirects', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('findings', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('recommendations', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('report_markdown', sa.Text(), nullable=True),
        sa.Column('cost_seconds', sa.Float(), nullable=True),
        sa.Column('check_version', sa.String(length=20), nullable=False, server_default='1.0.0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        if_not_exists=True,
    )
    op.create_index(
        'ix_link_analysis_checks_domain_created',
        'link_analysis_checks',
        ['domain', 'created_at'],
        if_not_exists=True,
    )
    op.create_index(
        'ix_link_analysis_checks_status',
        'link_analysis_checks',
        ['status'],
        if_not_exists=True,
    )

    # Create enum types (matching create_type=False in model.py)
    op.execute("DO $$ BEGIN "
               "CREATE TYPE link_analysis_overall_status AS ENUM ('pass', 'warning', 'fail', 'not_applicable'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; "
               "END $$;")
    op.execute("DO $$ BEGIN "
               "CREATE TYPE link_analysis_severity AS ENUM ('none', 'low', 'medium', 'high', 'critical'); "
               "EXCEPTION WHEN duplicate_object THEN NULL; "
               "END $$;")


def downgrade() -> None:
    op.drop_index('ix_link_analysis_checks_status', table_name='link_analysis_checks')
    op.drop_index('ix_link_analysis_checks_domain_created', table_name='link_analysis_checks')
    op.drop_table('link_analysis_checks')
    op.execute("DROP TYPE IF EXISTS link_analysis_severity;")
    op.execute("DROP TYPE IF EXISTS link_analysis_overall_status;")
