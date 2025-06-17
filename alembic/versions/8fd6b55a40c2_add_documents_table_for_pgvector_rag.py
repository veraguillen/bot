"""Add documents table for pgvector RAG

Revision ID: 8fd6b55a40c2
Revises: f493c28060bd
Create Date: 2025-06-11 07:48:08.737379

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# Importante: para manejar el tipo VECTOR, aunque no lo usemos directamente en la definición
# de la columna con op.create_table, es buena práctica tenerlo importado.
# Si tienes una librería como `sqlalchemy-pgvector`, impórtala. Si no, usa texto.
# from pgvector.sqlalchemy import VECTOR

# revision identifiers, used by Alembic.
revision: str = '8fd6b55a40c2'
down_revision: Union[str, None] = 'f493c28060bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema: Add pgvector extension and documents table for RAG."""
    # Habilita la extensión `pgvector`. Es idempotente y seguro ejecutarlo aquí.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    # Crea la tabla `documents`
    op.create_table(
        'documents',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('source', sa.String(length=255), nullable=True),
        # Definimos la columna VECTOR usando un literal de SQL.
        # 1536 es la dimensión para embeddings de OpenAI text-embedding-ada-002
        sa.Column('embedding', sa.TEXT(),  # Usamos TEXT como placeholder para sa.Column
                  server_default=None,  # Para evitar problemas con el tipo
                  comment="Columna para almacenar vectores. El tipo real es VECTOR(1536)."),
        sa.Column('metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    # Usamos execute para definir el tipo real de la columna, ya que Alembic
    # puede no tener un tipo `VECTOR` nativo.
    op.execute("ALTER TABLE documents ALTER COLUMN embedding TYPE VECTOR(1536) USING embedding::VECTOR(1536);")

    # Crea el índice HNSW para búsquedas rápidas. Es crucial para el rendimiento.
    op.create_index(
        'ix_documents_embedding',
        'documents',
        ['embedding'],
        unique=False,
        postgresql_using='hnsw',
        postgresql_with={'m': 16, 'ef_construction': 64},  # Parámetros por defecto, se pueden ajustar
        postgresql_ops={'embedding': 'vector_l2_ops'}  # Usar distancia L2, la más común
    )
    
    # Crear índice de texto para búsquedas por palabras clave
    op.execute("CREATE INDEX idx_documents_content_gin ON documents USING GIN (to_tsvector('spanish', content));")
    
    # Agregar función para actualizar timestamp de última modificación
    op.execute("""
    CREATE OR REPLACE FUNCTION update_timestamp()
    RETURNS TRIGGER AS $$
    BEGIN
       NEW.updated_at = CURRENT_TIMESTAMP;
       RETURN NEW;
    END;
    $$ language 'plpgsql';
    """)

    # Crear trigger para actualizar automáticamente el timestamp
    op.execute("""
    CREATE TRIGGER update_documents_timestamp
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE PROCEDURE update_timestamp();
    """)


def downgrade() -> None:
    """Downgrade schema: Remove documents table and related objects."""
    # Eliminar trigger primero
    op.execute("DROP TRIGGER IF EXISTS update_documents_timestamp ON documents;")
    
    # Eliminar función
    op.execute("DROP FUNCTION IF EXISTS update_timestamp();")
    
    # Eliminar índices
    op.drop_index('idx_documents_content_gin', table_name='documents')
    op.drop_index('ix_documents_embedding', table_name='documents')
    
    # Eliminar tabla
    op.drop_table('documents')
    
    # Normalmente no se deshabilita la extensión, ya que otras tablas podrían usarla.
    # Si estás seguro de que no es el caso, podrías descomentar la siguiente línea:
    # op.execute("DROP EXTENSION IF EXISTS vector;")

