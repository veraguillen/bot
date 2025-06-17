"""Fusion definitiva de ramas

Revision ID: 227c17acbe6d
Revises: 7caadc74023b, a4e6c9d2f758
Create Date: 2025-06-17 17:46:14.082693

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '227c17acbe6d'
down_revision: Union[str, None] = ('7caadc74023b', 'a4e6c9d2f758')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
