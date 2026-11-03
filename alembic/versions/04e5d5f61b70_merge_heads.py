"""merge heads

Revision ID: 04e5d5f61b70
Revises: 9aa6982d9c88, f8a9b0c1d2e3
Create Date: 2026-11-03 15:43:13.558881

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '04e5d5f61b70'
down_revision: Union[str, Sequence[str], None] = ('9aa6982d9c88', 'f8a9b0c1d2e3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
