from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool, create_engine # create_engine ya estaba
from alembic import context # context es el módulo
from dotenv import load_dotenv
import os
import sys

# Load environment variables
load_dotenv()

# Add project root to Python path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, PROJECT_ROOT)

# Import models
from app.core.database import Base
from app.models.user_state import UserState
from app.models import Company, Interaction, Appointment

# --- ESTA ES LA INSTANCIA DEL OBJETO CONFIG DE ALEMBIC ---
# 'config' (minúsculas) es la instancia del Alembic Config object que se pasa
# al script env.py. Contiene los valores del .ini y los args de línea de comando.
config = context.config # <--------------------------------------- ¡CLAVE!

def get_url():
    """Get database URL with proper driver configuration"""
    # Intentar obtener de la configuración de Alembic primero, si ya fue establecida
    # por ejemplo, desde la línea de comandos -x sqlalchemy.url=...
    # o si set_main_option fue llamado antes
    url_from_config = config.get_main_option("sqlalchemy.url")
    if url_from_config:
        # Asegurar que la URL (ya sea de DATABASE_URL o construida) use el driver síncrono y sslmode
        if "asyncpg" in url_from_config:
            url_from_config = url_from_config.replace("postgresql+asyncpg", "postgresql+psycopg2")
        if "sslmode" not in url_from_config:
            url_from_config += ("?" if "?" not in url_from_config else "&") + "sslmode=require"
        return url_from_config
    
    # Si no, construir desde variables de entorno o fallback
    env_url = os.getenv("DATABASE_URL")
    pg_user = os.getenv("PGUSER")
    pg_pass = os.getenv("PGPASSWORD")
    pg_host = os.getenv("PGHOST")
    pg_db = os.getenv("PGDATABASE")
    pg_port = os.getenv("PGPORT", "5432")

    if all([pg_user, pg_pass, pg_host, pg_db]):
        # Para psycopg2, sslmode en la URL es suficiente.
        # Asegúrate que PGPASSWORD no tenga caracteres que rompan la URL o usa quote_plus
        current_url = f"postgresql+psycopg2://{pg_user}:{pg_pass}@{pg_host}:{pg_port}/{pg_db}?sslmode=require"
    elif env_url:
        current_url = env_url
        if "asyncpg" in current_url:
            current_url = current_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
        if "sslmode" not in current_url:
            current_url += ("?" if "?" not in current_url else "&") + "sslmode=require"
    else:
        print("ADVERTENCIA: Usando URL de fallback hardcodeada para Alembic. Configura DATABASE_URL o PG* vars.")
        current_url = "postgresql+psycopg2://useradmin:Chat8121943.@chatbot-iram.postgres.database.azure.com:5432/chatbot_db?sslmode=require"
    
    # Establecer la URL construida en la configuración de Alembic para uso futuro
    config.set_main_option("sqlalchemy.url", current_url)
    print(f"Alembic usará la URL (construida/fallback): {current_url}")
    return current_url


def get_connect_args():
    """Configure connect_args. SSL es manejado por la URL para psycopg2."""
    # psycopg2 toma sslmode de la URL. connect_timeout es válido para psycopg2.
    return {
        # "sslmode": "require", # Quitado porque ya está en la URL y causaba el TypeError anterior
        "connect_timeout": 30
    }

# Configure logging from alembic.ini
# Usa la variable 'config' (minúsculas) que es la instancia del Config object
if config.config_file_name is not None: # <----------------------- CORREGIDO
    fileConfig(config.config_file_name)

# Set target metadata for autogenerate support
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url() # get_url ahora también establece config.set_main_option
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # La URL ya debería estar establecida en 'config' por la llamada a get_url()
    # que ocurre cuando se carga el módulo (si se llama desde el ámbito global)
    # o la primera vez que se llama a get_url().
    # Para asegurar, podemos llamarla aquí si no se ha establecido.
    db_url = config.get_main_option("sqlalchemy.url")
    if not db_url: # Si get_url() no fue llamado antes globalmente para establecerlo
        db_url = get_url() # Esto también llamará a config.set_main_option

    engine = create_engine(
        db_url, # Usar la URL de la configuración
        poolclass=pool.NullPool,
        connect_args=get_connect_args()
    )

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True # Buena adición para la comparación de tipos
        )

        with context.begin_transaction():
            context.run_migrations()

# Run migrations
if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
