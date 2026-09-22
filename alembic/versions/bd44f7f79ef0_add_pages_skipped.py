"""add pages_skipped

Revision ID: bd44f7f79ef0
Revises: abc123
Create Date: 2026-09-22 08:13:03.733880

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd44f7f79ef0'
down_revision: Union[str, Sequence[str], None] = 'abc123'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('crawl_jobs', sa.Column('pages_skipped', sa.Integer(), server_default='0', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('crawl_jobs', 'pages_skipped')
