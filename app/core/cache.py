"""
Sistema de caché para respuestas del LLM.
Implementa un caché usando Redis o memoria según disponibilidad.
"""
import redis
import json
import hashlib
import logging
from typing import Optional, Dict, Any
from app.core.config import settings

logger = logging.getLogger(__name__)

class LLMCache:
    """
    Caché para respuestas del LLM con soporte para Redis.
    Si Redis no está disponible, utiliza un caché en memoria.
    """
    
    _instance = None
    
    def __new__(cls):
        """Implementación Singleton para evitar múltiples instancias de caché."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Inicializa el cliente Redis o el caché en memoria."""
        try:
            # Intentar usar configuración desde settings, con valores por defecto
            redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
            self.redis = redis.from_url(redis_url)
            self.ttl = getattr(settings, "CACHE_TTL", 3600)  # 1 hora por defecto
            self.use_redis = True
            logger.info(f"LLM Cache inicializado con Redis: {redis_url}")
        except Exception as e:
            logger.warning(f"No se pudo inicializar Redis: {e}. Usando caché en memoria.")
            self.use_redis = False
            self.memory_cache = {}
    
    def key_for_prompt(self, prompt: str, **kwargs) -> str:
        """
        Genera una clave única para un prompt y sus parámetros.
        La clave es determinista para los mismos parámetros de entrada.
        """
        # Filtrar parámetros, excluyendo objetos no serializables
        filtered_kwargs = {}
        for k, v in kwargs.items():
            if isinstance(v, (str, int, float, bool, list, dict)) or v is None:
                filtered_kwargs[k] = v
        
        # Crear un objeto serializable para la clave
        data = {"prompt": prompt, **filtered_kwargs}
        serialized = json.dumps(data, sort_keys=True)
        
        # Generar hash para la clave
        return f"llm:{hashlib.md5(serialized.encode()).hexdigest()}"
    
    def get(self, key: str) -> Optional[str]:
        """Obtiene una respuesta cacheada por su clave."""
        try:
            if self.use_redis:
                data = self.redis.get(key)
                return data.decode() if data else None
            else:
                return self.memory_cache.get(key)
        except Exception as e:
            logger.warning(f"Error leyendo de caché: {e}")
            return None
    
    def set(self, key: str, value: str) -> bool:
        """
        Guarda una respuesta en el caché.
        Retorna True si se guardó correctamente, False en caso contrario.
        """
        try:
            if self.use_redis:
                self.redis.setex(key, self.ttl, value)
            else:
                self.memory_cache[key] = value
            return True
        except Exception as e:
            logger.warning(f"Error guardando en caché: {e}")
            return False

# Instancia global
llm_cache = LLMCache()
