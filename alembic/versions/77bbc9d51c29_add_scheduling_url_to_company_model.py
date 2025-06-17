"""add_scheduling_url_to_company_model

Revision ID: 77bbc9d51c29
Revises: 0d3f2a8e9456
Create Date: 2025-06-13 14:19:58.475814

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '77bbc9d51c29'
down_revision: Union[str, None] = '0d3f2a8e9456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
