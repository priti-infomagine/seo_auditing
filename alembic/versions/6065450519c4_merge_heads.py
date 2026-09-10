"""merge heads

Revision ID: 6065450519c4
Revises: aabbccdd001, f5a6b7c8d9e0
Create Date: 2026-09-10 16:33:59.478997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6065450519c4'
down_revision: Union[str, Sequence[str], None] = ('aabbccdd001', 'f5a6b7c8d9e0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
