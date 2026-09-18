"""merge final migration heads

Revision ID: c65858aed041
Revises: a1b2c3d4, f6a7b8c9d0e1
Create Date: 2026-09-15 14:37:10.807497

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c65858aed041'
down_revision: Union[str, Sequence[str], None] = ('a1b2c3d4', 'f6a7b8c9d0e1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
