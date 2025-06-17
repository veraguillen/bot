"""Add pgvector extension

Revision ID: d0e0dfe8e49c
Revises: 
Create Date: 2025-06-11 20:07:24.315073

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd0e0dfe8e49c'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Este es el único comando que ejecutamos. Es seguro y solo crea
    # la extensión si no existe.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

def downgrade() -> None:
    # En general, no se recomienda eliminar la extensión en un downgrade
    # por si otros datos dependen de ella, pero por completitud, sería así:
    op.execute("DROP EXTENSION IF EXISTS vector;")
