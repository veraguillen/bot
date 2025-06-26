# app/core/config.py
import os
from pathlib import Path
from dotenv import load_dotenv

# --- CARGA EXPLÍCITA Y TEMPRANA DE .ENV ---
# Esto garantiza que las variables estén disponibles para el resto del módulo.
PROJECT_ROOT_DIR_FOR_ENV = Path(__file__).resolve().parent.parent.parent
dotenv_path = PROJECT_ROOT_DIR_FOR_ENV / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
# ----------------------------------------------

from typing import Optional, List, Set
from pydantic import PostgresDsn, Field, HttpUrl, validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# --- 1. Definición de Rutas Base (independiente de la clase Settings) ---
# Se calcula una sola vez cuando el módulo se importa.
# Esto funciona en cualquier SO y dentro de Docker.
PROJECT_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT_DIR / "data"
LOG_DIR = PROJECT_ROOT_DIR / "logs"

# --- 2. Clase de Configuración Principal ---
class Settings(BaseSettings):
    """
    Centraliza toda la configuración de la aplicación.
    Lee desde variables de entorno y/o un archivo .env.
    """
    # --- Información del Proyecto ---
    PROJECT_NAME: str = "Chatbot Multimarca Beta"
    PROJECT_VERSION: str = "1.0.1"

    # --- Configuración del Servidor y Entorno ---
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    # FIX: Re-introducido para compatibilidad con el módulo de logging
    LOG_FORMAT: str = '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    PROJECT_SITE_URL: str = "http://localhost:8000"

    # --- Base de Datos (PostgreSQL en Azure) ---
    # Pydantic validará la URL y la mantendrá como un objeto DSN.
    # La conversión a string se hará en database.py.
    DATABASE_URL: PostgresDsn

    # --- IA: RAG, Embeddings y PGVector ---
    EMBEDDING_MODEL_NAME: str = "sentence-transformers/all-mpnet-base-v2"
    VECTOR_COLLECTION_NAME: str = "chatbot_docs_v1"
    # Optimizado: 4 fragmentos es el punto óptimo para balance precisión/contexto
    RAG_DEFAULT_K: int = 4
    # Reducido de 2 a 1: evita sobrecargar el contexto con fragmentos redundantes
    RAG_K_FETCH_MULTIPLIER: int = 1
    
    # --- Configuraciones adicionales para procesamiento de texto ---
    # Tamaño óptimo de fragmentos: balance entre contexto y precisión
    CHUNK_SIZE: int = 1200
    # Solapamiento para mantener continuidad entre fragmentos
    CHUNK_OVERLAP: int = 150
    # Umbral mínimo de similitud para filtrar resultados irrelevantes
    RAG_SIMILARITY_THRESHOLD: float = 0.3

    # --- Seguridad y CORS ---
    ALLOWED_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Lista de orígenes permitidos para CORS. Usar lista separada por comas en env."
    )
    
    # --- Integraciones externas (variables opcionales) ---
    # Estas variables son opcionales y no causarán error si no están definidas
    # OPENROUTER_CHAT_ENDPOINT: Optional[str] = None  # COMENTADO: Ahora es requerido
    
    # --- Caché y Rendimiento ---
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="URL para la conexión a Redis. Formato: redis://host:puerto/db"
    )
    CACHE_TTL: int = Field(
        default=3600,
        description="Tiempo en segundos que las respuestas se mantienen en caché"
    )
    
    # --- Monitoreo y Telemetría Azure --- 
    APPLICATIONINSIGHTS_CONNECTION_STRING: Optional[str] = Field(
        default=None,
        description="Connection string para Azure Application Insights"
    )
    
    # --- IA: LLM (OpenRouter.ai) ---
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL_CHAT: str = "meta-llama/llama-3-8b-instruct"  # Valor por defecto del .env
    OPENROUTER_CHAT_ENDPOINT: str = "https://openrouter.ai/api/v1"  # URL base por defecto pero requerida
    LLM_TEMPERATURE: float = 0.7  # Actualizado a 0.7
    LLM_MAX_TOKENS: int = 1000  # Ajustado a 1000 para coincidir con el valor en .env
    LLM_HTTP_TIMEOUT: float = 45.0  # Ajustado a 45.0 para coincidir con el valor en .env
    LLM_TOP_P: float = 1.0  # Nuevo parámetro
    LLM_FREQUENCY_PENALTY: float = 0.0  # Nuevo parámetro
    LLM_PRESENCE_PENALTY: float = 0.0  # Nuevo parámetro
    
    # --- Palabras clave para salir de la conversación ---
    EXIT_CONVERSATION_KEYWORDS: List[str] = ["salir", "adiós", "cancelar", "terminar", "stop", "chao", "bye", "hasta luego"]

    # --- Integración con Meta (WhatsApp) ---
    WHATSAPP_PHONE_NUMBER_ID: str
    WHATSAPP_ACCESS_TOKEN: str
    # VERIFY_TOKEN es el alias de entorno para WHATSAPP_VERIFY_TOKEN
    WHATSAPP_VERIFY_TOKEN: str = Field(validation_alias="VERIFY_TOKEN")
    META_API_VERSION: str = "v22.0"
    # FIX: Re-introducido como opcional para compatibilidad con el TokenManager
    MESSENGER_PAGE_ACCESS_TOKEN: Optional[str] = None
    
    # --- Integración con Calendly ---
    CALENDLY_API_KEY: Optional[str] = None
    CALENDLY_EVENT_TYPE_URI: Optional[str] = None
    CALENDLY_GENERAL_SCHEDULING_LINK: Optional[str] = None

    # --- Rutas de Directorios (calculadas) ---
    # Estas son propiedades de solo lectura que usan las constantes definidas arriba.
    @property
    def LOG_DIR_PATH(self) -> Path:
        return LOG_DIR

    @property
    def DATA_DIR_PATH(self) -> Path:
        return DATA_DIR

    # --- Configuración de Pydantic ---
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Validador para asegurar que LOG_LEVEL sea un valor válido
    @validator("LOG_LEVEL")
    def validate_log_level(cls, v):
        """Valida que el nivel de log sea uno de los valores permitidos."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"LOG_LEVEL debe ser uno de: {', '.join(valid_levels)}")
        return v.upper()
        
    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_allowed_origins(cls, v):
        """Parsea la lista de orígenes permitidos desde una variable de entorno separada por comas."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


# --- 3. Instancia Singleton de la Configuración ---
# Se crea una vez y se importa en el resto de la aplicación.
try:
    # Crear los directorios necesarios al inicio
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    settings = Settings()

except Exception as e:
    # Si la configuración falla, la aplicación no puede continuar.
    print(f"!!!!!!!!!!!!!! ERROR CRÍTICO AL CARGAR LA CONFIGURACIÓN !!!!!!!!!!!!!!")
    print(f"Error: {e}")
    print(f"Asegúrate de que todas las variables de entorno requeridas estén definidas en tu archivo .env o en el sistema.")
    print(f"Ruta del .env esperada: {PROJECT_ROOT_DIR / '.env'}")
    print(f"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
    exit(1)