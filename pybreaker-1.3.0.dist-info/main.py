"""
Main entry point for the FastAPI application.
"""
import os
import sys
import logging
from pathlib import Path

# ======== CONFIGURACIÓN DE RUTAS DE IMPORTACIÓN ========
# Determinar ruta absoluta del directorio raíz del proyecto
PROJECT_ROOT = Path(__file__).resolve().parent
    
# Añadir la ruta del proyecto al sys.path si no está ya
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Configuración de logging optimizada para Azure (envía a stdout)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout,
)
logger = logging.getLogger("chatbot_app_loader")

# Importar la instancia app desde el paquete app donde ya está completamente configurada
try:
    # Importamos la instancia de FastAPI ya configurada en app/__init__.py
    from app import app
    from fastapi import Response, status
    
    if app is None:
        logger.critical("La instancia 'app' importada desde el paquete 'app' es None")
        sys.exit(1)
    
    # Añadir endpoint de health check para monitoreo en Azure
    @app.get("/health", status_code=status.HTTP_200_OK, tags=["Monitoring"])
    def perform_health_check():
        """Verifica que el servicio esté activo y responde con 200 OK."""
        # En una implementación completa, aquí se verificaría la conexión a la BD.
        return {"status": "ok"}
    
    logger.info(f"Aplicación FastAPI cargada correctamente desde el paquete 'app'")
    logger.info(f"Endpoint de health check registrado en /health")
    
    # Información adicional para diagnóstico en entornos de contenedor
    import os
    print(f"INFO: El archivo main.py ha completado su configuración. La variable 'app' está lista para Gunicorn.")
    print(f"INFO: Ruta actual: {os.getcwd()}, archivos en directorio: {os.listdir()}")
    print(f"INFO: Python path: {sys.path}")
except ImportError as e:
    logger.critical(f"Error crítico al importar la instancia 'app' desde el paquete 'app': {e}")
    sys.exit(1)

# Punto de entrada para ejecución directa
if __name__ == "__main__":
    import uvicorn
    from app.core.config import settings
    
    logger.info(f"Iniciando servidor con uvicorn desde main.py")
    
    uvicorn.run(
        "main:app",
        host=getattr(settings, "SERVER_HOST", "0.0.0.0"),
        port=int(getattr(settings, "SERVER_PORT", 8000)),
        reload=getattr(settings, "DEBUG", False)
    )
