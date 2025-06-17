"""add_scheduling_url_to_company_model

Revision ID: 0d3f2a8e9456
Revises: 3cc32c5aa1e6
Create Date: 2025-06-13 14:10:07.835611

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0d3f2a8e9456'
down_revision: Union[str, None] = '3cc32c5aa1e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: añade el campo scheduling_url a la tabla companies."""
    op.add_column('companies', sa.Column('scheduling_url', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema: elimina el campo scheduling_url de la tabla companies."""
    op.drop_column('companies', 'scheduling_url')
