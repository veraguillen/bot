"""merge all heads

Revision ID: 7caadc74023b
Revises: 77bbc9d51c29
Create Date: 2025-06-13 14:29:21.107793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7caadc74023b'
down_revision: Union[str, None] = '77bbc9d51c29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
