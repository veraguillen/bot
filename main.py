"""
Main entry point for the FastAPI application.
"""
import os
import sys
import logging
from pathlib import Path

# Configuración básica de logging para errores iniciales
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger("chatbot_app_loader")

# Asegurarse de que el directorio raíz esté en el path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Importar la instancia app desde el paquete app
try:
    # Importar settings primero para asegurar que la configuración esté cargada
    from app.core.config import settings
    
    # Luego importar la aplicación
    from app import app
    
    if app is None:
        logger.critical("La instancia 'app' importada desde el paquete 'app' es None")
        sys.exit(1)
        
    logger.info(f"Aplicación FastAPI cargada correctamente desde el paquete 'app'")
    
    # Información de diagnóstico
    logger.info(f"Directorio de trabajo: {os.getcwd()}")
    logger.info(f"Archivos en el directorio actual: {os.listdir()}")
    logger.info(f"Python path: {sys.path}")
    
except ImportError as e:
    logger.critical(f"Error crítico al importar la aplicación: {e}", exc_info=True)
    sys.exit(1)

except Exception as e:
    logger.critical(f"Error inesperado al iniciar la aplicación: {e}", exc_info=True)
    sys.exit(1)

# Punto de entrada para ejecución directa (usando uvicorn)
if __name__ == "__main__":
    import uvicorn
    
    # Configuración del servidor
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    
    logger.info(f"Iniciando servidor con uvicorn desde main.py en http://{host}:{port}")
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )
