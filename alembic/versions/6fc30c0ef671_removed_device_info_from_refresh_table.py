"""removed device info from refresh table

Revision ID: 6fc30c0ef671
Revises: 8c2dae25c897
Create Date: 2026-07-31 11:10:35.215279

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6fc30c0ef671'
down_revision: Union[str, Sequence[str], None] = '8c2dae25c897'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_column('refresh_tokens', 'os')
    op.drop_column('refresh_tokens', 'browser')
    op.drop_column('refresh_tokens', 'device_type')
    op.drop_column('refresh_tokens', 'device_name')

def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        'refresh_tokens',
        sa.Column(
            'device_name',
            sa.String(length=255),
            nullable=True,
        ),
    )
    op.add_column(
        'refresh_tokens',
        sa.Column(
            'device_type',
            sa.String(length=50),
            nullable=True,
        ),
    )
    op.add_column(
        'refresh_tokens',
        sa.Column(
            'browser',
            sa.String(length=100),
            nullable=True,
        ),
    )
    op.add_column(
        'refresh_tokens',
        sa.Column(
            'os',
            sa.String(length=100),
            nullable=True,
        ),
    )
