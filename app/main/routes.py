# app/main/routes.py
from fastapi import APIRouter, Query, Depends, Request, HTTPException, Body, BackgroundTasks
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, Optional
import json
import os
from datetime import datetime, timezone

# Importamos el meta_router para WhatsApp API
from ..api.meta import meta_router

# Importar la instancia 'settings' y la función 'get_db_session'
from ..core.config import settings # Importa la instancia settings ya inicializada
from ..core.database import get_db_session # NOMBRE CORRECTO de la dependencia de BD
from .webhook_handler import process_webhook_payload
from ..utils.logger import logger

router = APIRouter()

# Incluimos el meta_router como parte del router principal
router.include_router(meta_router, prefix="/meta", tags=["Meta API"])

# Acceder al token de verificación desde el objeto settings
# Asegúrate de que 'WHATSAPP_VERIFY_TOKEN' sea el nombre del atributo en tu clase Settings
# que se popula desde la variable de entorno VERIFY_TOKEN.
if settings and hasattr(settings, 'WHATSAPP_VERIFY_TOKEN'):
    VERIFY_TOKEN_FROM_SETTINGS = settings.WHATSAPP_VERIFY_TOKEN
else:
    VERIFY_TOKEN_FROM_SETTINGS = None # Fallback si settings o el atributo no están
    logger.error("CRÍTICO [routes.py]: No se pudo cargar WHATSAPP_VERIFY_TOKEN desde settings. La verificación del Webhook fallará.")


@router.get("/", tags=["Root"])
async def read_root(request: Request):
    # Este endpoint es opcional, principalmente para pruebas de que la app está viva.
    port = os.getenv("WEBSITES_PORT", "Puerto no definido (revisar WEBSITES_PORT en Azure App Service)")
    db_status = "desconocido"
    rag_status = "desconocido"
    
    # Acceder al estado de la aplicación de forma segura usando hasattr
    db_ok = hasattr(request.app.state, 'is_db_ready') and request.app.state.is_db_ready
    db_status = "lista" if db_ok else "no_lista"
    
    rag_ok = hasattr(request.app.state, 'is_rag_ready') and request.app.state.is_rag_ready
    rag_status = "listo" if rag_ok else "no_listo"
        
    return {
        "project": settings.PROJECT_NAME, 
        "version": settings.PROJECT_VERSION,
        "status_message": "Servicio Activo",
        "database_status": db_status,
        "rag_status": rag_status,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "docs_url": "/docs",
        "redoc_url": "/redoc"
    }

@router.get("/webhook", response_class=PlainTextResponse, tags=["Webhook Verification"])
async def verify_webhook_route(
    # Los parámetros vienen de la query de la URL, FastAPI los mapea
    request: Request,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token") # Este es el token que envía Meta
):
    """Endpoint de verificación de webhook (redirecciona al nuevo endpoint en api/meta)"""
    logger.info(f"LEGACY GET /webhook: Redirigiendo solicitud de verificación a meta_router")
    
    # Importar el endpoint meta_router.webhook_verification
    from ..api.meta import webhook_verification
    
    # Redirigir al nuevo endpoint manteniendo compatibilidad
    return await webhook_verification(request, hub_mode, hub_challenge, hub_verify_token)

@router.post("/webhook", tags=["Webhook Messages"])
async def receive_webhook_route(
    request: Request,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db_session: AsyncSession = Depends(get_db_session)
):
    """Endpoint legacy para recepción de mensajes (redirecciona al nuevo endpoint en api/meta)"""
    logger.info("LEGACY POST /webhook: Redirigiendo solicitud de mensajes a meta_router")
    
    # Importar el endpoint meta_router.receive_webhook_events
    from ..api.meta import receive_webhook_events
    
    # Redirigir al nuevo endpoint manteniendo compatibilidad
    return await receive_webhook_events(request, background_tasks, db_session)