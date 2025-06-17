"""
Migración para añadir columna conversation_history a tabla user_states.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# Identificador de revisión
revision = 'add_conversation_history'
down_revision = None  # Esto debe ser ajustado según tu historial de migraciones
branch_labels = None
depends_on = None

def upgrade():
    """
    Añade la columna conversation_history a la tabla user_states.
    """
    op.add_column(
        'user_states',
        sa.Column('conversation_history', JSON, nullable=True)
    )

def downgrade():
    """
    Elimina la columna conversation_history de la tabla user_states.
    """
    op.drop_column('user_states', 'conversation_history')
