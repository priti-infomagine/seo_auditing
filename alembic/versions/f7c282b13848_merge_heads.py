"""merge heads

Revision ID: f7c282b13848
Revises: b1c2d3e4f5a6, c2d3e4f5a6b7
Create Date: 2026-09-28 17:34:41.901748

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7c282b13848'
down_revision: Union[str, Sequence[str], None] = ('b1c2d3e4f5a6', 'c2d3e4f5a6b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
