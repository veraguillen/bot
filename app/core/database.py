# app/core/database.py
import json
import logging
import os
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any
from dotenv import load_dotenv

# --- CARGA EXPLÍCITA Y LOCAL DE .ENV ---
# Se carga aquí para asegurar que las variables estén disponibles para este módulo.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    logging.getLogger("database.env").info(f"Variables de entorno cargadas desde {dotenv_path}")
# ----------------------------------------

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import text

# --- Base para los modelos SQLAlchemy ---
Base = declarative_base()

# --- Variables globales (no se inicializan al importar el módulo) ---
_engine: Optional[AsyncEngine] = None
_session_maker: Optional[async_sessionmaker[AsyncSession]] = None

# --- Variables públicas para retrocompatibilidad ---
# (Mantiene compatibilidad con el código existente que importa AsyncSessionLocal)
AsyncSessionLocal: Optional[async_sessionmaker[AsyncSession]] = None

# --- Función para acceder al motor inicializado ---
def get_db_engine() -> Optional[AsyncEngine]:
    """Devuelve el engine asíncrono inicializado o None si no está disponible.
    Usar esta función en lugar de importar _engine directamente.
    """
    return _engine

# --- Configuración de logging independiente de la aplicación ---
_db_logger = logging.getLogger("database")
if not _db_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(formatter)
    _db_logger.addHandler(handler)
    _db_logger.setLevel(logging.INFO)


async def initialize_database() -> bool:
    """
    Inicialización perezosa del motor de base de datos y fábrica de sesiones.
    Esta función debe ser llamada explícitamente durante el lifespan de la aplicación,
    garantizando que la configuración esté completamente cargada.
    
    Returns:
        bool: True si la inicialización fue exitosa, False en caso contrario.
    """
    global _engine, _session_maker
    
    # Importación tardía de la configuración para evitar dependencias circulares
    # y asegurar que las variables de entorno ya estén cargadas
    try:
        from app.core.config import settings
        from app.utils.logger import logger as app_logger
        logger = app_logger  # Usar el logger de la aplicación si está disponible
    except ImportError:
        logger = _db_logger
        logger.warning("Usando logger independiente para la base de datos")
        try:
            from app.core.config import settings
        except ImportError:
            logger.critical("No se pudo importar la configuración (settings)")
            return False
    
    # Verificar que DATABASE_URL esté configurada
    if not hasattr(settings, 'DATABASE_URL') or not settings.DATABASE_URL:
        logger.critical("DATABASE_URL no está configurada en settings. Verifique el archivo .env.")
        return False
    
    # --------------------------------------------------------------------------
    # Convertir el objeto PostgresDsn de Pydantic a string para SQLAlchemy
    # --------------------------------------------------------------------------
    db_url_str = str(settings.DATABASE_URL)
    
    # Ofuscar credenciales para logs
    if '@' in db_url_str:
        protocol_auth, location = db_url_str.split('@', 1)
        protocol_parts = protocol_auth.split('://', 1)
        protocol = protocol_parts[0] if len(protocol_parts) > 1 else 'postgresql'
        log_url = f"{protocol}://***:***@{location}"
    else:
        log_url = db_url_str
        
    logger.info(f"Iniciando conexión a la base de datos: {log_url}")
    
    # Construir opciones para el motor de base de datos
    engine_options: Dict[str, Any] = {
        "echo": getattr(settings, 'SQL_ECHO', False),
        "pool_pre_ping": True,
        "pool_recycle": 3600,  # Recicla conexiones cada hora
        "json_serializer": lambda obj: json.dumps(obj, ensure_ascii=False)
    }
    
    # Opciones de SSL (garantizar siempre SSL en entornos de producción o Azure)
    environment = os.getenv("ENVIRONMENT", "").lower()
    is_production = environment in ["production", "prod", "azure"]
    
    # En entorno Azure/Producción, asegurarse de usar SSL pero SIN añadirlo a la URL para AsyncPG
    # ya que este driver no utiliza parámetros de URL sino connect_args
    is_asyncpg = "postgresql+asyncpg" in db_url_str.lower()
    
    # Para psycopg2 (no asyncpg) añadir el sslmode a la URL
    if not is_asyncpg and "?sslmode=" not in db_url_str.lower() and "&sslmode=" not in db_url_str.lower():
        connector = "&" if "?" in db_url_str else "?"
        db_url_str = f"{db_url_str}{connector}sslmode=require"
        logger.info(f"SSL forzado para entorno de producción: URL actualizada con sslmode=require")
    
    # Configuración simplificada de SSL para AsyncPG
    if is_asyncpg:
        # Para asyncpg 0.30.0 solo necesitamos ssl=True
        logger.info("Configurando SSL simplificado para driver asyncpg")
        engine_options["connect_args"] = {
            "ssl": True
        }
    
    try:
        # Crear el motor de forma segura
        _engine = create_async_engine(db_url_str, **engine_options)
        
        # Nos conectamos para ejecutar el comando de la extensión por separado.
        async with _engine.connect() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.commit() # Aseguramos que la transacción se complete
        _db_logger.info("DB_INIT: Verificación/Creación de la extensión 'vector' completada.")
        
        # Probar la conexión antes de continuar
        async with _engine.connect() as connection:
            result = await connection.execute(text("SELECT 1"))
            if result.scalar_one() != 1:
                raise ConnectionError("La prueba de conexión 'SELECT 1' falló")
        
        # Crear la fábrica de sesiones solo después de verificar la conexión
        _session_maker = async_sessionmaker(
            bind=_engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        
        # Asignar a variable de compatibilidad para código existente
        global AsyncSessionLocal
        AsyncSessionLocal = _session_maker
        
        logger.info("✓ Conexión a la base de datos establecida y verificada correctamente")
        return True
        
    except Exception as e:
        logger.critical(f"❌ Error al inicializar la base de datos: {e}", exc_info=True)
        _engine = None
        _session_maker = None
        return False


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependencia de FastAPI para obtener una sesión de base de datos.
    La sesión se cierra automáticamente al final del contexto.
    """
    # Verificación de inicialización tardía
    if _session_maker is None:
        _db_logger.error("Intento de acceder a la base de datos antes de su inicialización")
        raise RuntimeError("La base de datos no ha sido inicializada. Verifique el lifespan de la aplicación.")
    
    # Crear una sesión de base de datos y devolverla    
    async with _session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            _db_logger.error(f"Excepción en la sesión de base de datos, ejecutando rollback: {e}")
            raise


async def close_database_engine():
    """
    Cierra el pool de conexiones del motor de la base de datos.
    Se llama durante el 'lifespan' de apagado.
    """
    global _engine, _session_maker
    
    if _engine is not None:
        _db_logger.info("Cerrando conexiones a la base de datos...")
        await _engine.dispose()
        _engine = None
        _session_maker = None
        _db_logger.info("Conexiones de base de datos cerradas correctamente")
        return True
    return False