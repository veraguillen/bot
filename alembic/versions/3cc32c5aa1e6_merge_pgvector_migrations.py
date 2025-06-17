"""merge_pgvector_migrations

Revision ID: 3cc32c5aa1e6
Revises: 8fd6b55a40c2, d0e0dfe8e49c
Create Date: 2025-06-13 14:09:50.410491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3cc32c5aa1e6'
down_revision: Union[str, None] = ('8fd6b55a40c2', 'd0e0dfe8e49c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
