# app/utils/logger.py
import logging
import sys
import os
import uuid
import contextvars
from pathlib import Path
from logging.handlers import RotatingFileHandler
import threading
from typing import Optional, Dict, Any

# REFACTOR: Ahora evitamos dependencias circulares importando settings solo cuando sea necesario
# y no a nivel de módulo, para que otros módulos puedan importar logger sin problemas

# Variable de contexto para almacenar el request_id
request_id_var = contextvars.ContextVar('request_id', default=None)

# Configuración inicial del logger
logger = logging.getLogger("ChatbotApp")
logger.setLevel(logging.INFO)  # Nivel por defecto hasta que se configure

# Flag para evitar configuración múltiple
_logger_configured = False

# Bloqueo para concurrencia
_logger_lock = threading.Lock()


def set_request_id(req_id: Optional[str] = None) -> str:
    """
    Establece un ID de solicitud para la ejecución actual.
    Si no se proporciona un ID, genera uno nuevo con UUID.
    Utiliza contextvars para almacenar el ID de forma segura para threads.
    
    Args:
        req_id: ID de solicitud opcional. Si es None, se generará uno nuevo.
        
    Returns:
        El ID de solicitud establecido.
    """
    if req_id is None:
        # Generar un UUID4 como request_id por defecto
        req_id = f"req-{uuid.uuid4().hex[:12]}"
    
    # Almacena el ID en el contexto del thread actual
    request_id_var.set(req_id)
    return req_id


def get_request_id() -> Optional[str]:
    """
    Obtiene el ID de solicitud para la ejecución actual.
    
    Returns:
        El ID de solicitud actual o None si no está establecido.
    """
    return request_id_var.get()


def clear_request_id() -> None:
    """
    Elimina el ID de solicitud del contexto actual.
    """
    request_id_var.set(None)


class RequestIdFilter(logging.Filter):
    """
    Filtro de logging que agrega el request_id a todos los registros.
    """
    def filter(self, record):
        # Obtener el ID de solicitud actual y agregarlo al registro
        request_id = get_request_id()
        record.request_id = request_id if request_id else "-"
        return True

def setup_logging():
    """
    Configura el sistema de logging de forma auto-contenida.
    Se llama automáticamente cuando este módulo es importado.
    """
    global _logger_configured
    
    with _logger_lock:
        if _logger_configured:
            return
        
        print(f"[logger.py] Configurando el logger para PID {os.getpid()}")
        
        # Importar settings solo cuando sea necesario
        try:
            from app.core.config import settings
            
            # Limpiar los handlers existentes
            if logger.handlers:
                logger.handlers.clear()
            
            # Desactivar propagación para evitar duplicación
            logger.propagate = False
            
            # Establecer el nivel de log
            log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)
            logger.setLevel(log_level)
            
            # Aplicar el filtro de request_id a todos los registros
            logger.addFilter(RequestIdFilter())
            
            # Formato del log con request_id incluido
            default_format = '%(asctime)s - %(name)s - %(levelname)s - [%(request_id)s] [%(filename)s:%(lineno)d] - %(message)s'
            log_format = settings.LOG_FORMAT if hasattr(settings, 'LOG_FORMAT') else default_format
            formatter = logging.Formatter(log_format)
            
            # Handler para consola
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)
            
            # Handler para archivo
            log_dir = settings.LOG_DIR_PATH if hasattr(settings, 'LOG_DIR_PATH') else Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)
            
            log_file = log_dir / "app.log"
            
            try:
                file_handler = RotatingFileHandler(
                    filename=log_file,
                    maxBytes=10 * 1024 * 1024,  # 10 MB
                    backupCount=5,
                    encoding='utf-8'
                )
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
                print(f"[logger.py] Logging a archivo configurado: {log_file}")
            except Exception as e:
                print(f"[logger.py] Error al configurar el log a archivo: {e}", file=sys.stderr)
                # Continuar con solo el handler de consola
            
            logger.info(f"Logger configurado para el proceso {os.getpid()} en nivel {settings.LOG_LEVEL}")
            _logger_configured = True
            
        except ImportError as e:
            # Configuración de emergencia si no podemos importar settings
            print(f"[logger.py] No se pudo importar settings: {e}. Usando configuración de emergencia.", file=sys.stderr)
            
            # Configurar un handler de emergencia
            if not logger.handlers:
                handler = logging.StreamHandler(sys.stderr)
                formatter = logging.Formatter('%(asctime)s - %(name)s - EMERGENCY - %(levelname)s - %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
                logger.setLevel(logging.INFO)
            
            _logger_configured = True
        
        except Exception as e:
            print(f"[logger.py] Error al configurar el logger: {e}", file=sys.stderr)
            
            # Asegurar que haya al menos un handler básico
            if not logger.handlers:
                handler = logging.StreamHandler(sys.stderr)
                formatter = logging.Formatter('%(asctime)s - EMERGENCY - %(message)s')
                handler.setFormatter(formatter)
                logger.addHandler(handler)
                logger.setLevel(logging.ERROR)
            
            _logger_configured = True

# Auto-configurar el logger cuando el módulo es importado
setup_logging()