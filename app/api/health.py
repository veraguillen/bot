"""
Módulo para monitoreo de salud (health) de la aplicación.
Proporciona endpoints para verificar el estado de los componentes críticos.
"""
import logging
from typing import Dict, Any
from fastapi import APIRouter, Depends, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import text

from app.core.database import get_db_session

# Configurar logger específico para este módulo
logger = logging.getLogger(__name__)

# Crear router para los endpoints de health
health_router = APIRouter(tags=["Health Check"])

@health_router.get("/health/", status_code=status.HTTP_200_OK)
async def health_check(request: Request, db: AsyncSession = Depends(get_db_session)) -> Dict[str, Any]:
    """
    Verifica el estado de las dependencias críticas: BD Relacional y RAG.
    """
    logger.info("Verificando estado de salud de la aplicación...")

    # 1. Verificar la base de datos relacional
    db_status = {"status": "ok", "message": "Conexión exitosa."}
    try:
        # ¡CLAVE! Envolvemos la query en text()
        await db.execute(text("SELECT 1"))
    except Exception as e:
        logger.error(f"Error verificando la conexión a la base de datos: {e}")
        db_status = {"status": "error", "message": str(e)}

    # 2. Verificar el sistema RAG usando el estado guardado en la app
    is_rag_ready = hasattr(request.app.state, 'is_rag_ready') and request.app.state.is_rag_ready
    rag_status = {
        "status": "ok" if is_rag_ready else "error",
        "message": "Sistema RAG inicializado correctamente." if is_rag_ready else "El sistema RAG no está listo."
    }
    
    # 3. Determinar el estado general
    final_status = "ok" if db_status["status"] == "ok" and rag_status["status"] == "ok" else "error"
    
    response_payload = {
        "application_status": final_status,
        "dependencies": {
            "relational_db": db_status,
            "vector_db_rag": rag_status
        }
    }
    
    # Si algo falla, devolvemos un código de error
    if final_status == "error":
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=response_payload)
        
    return response_payload
