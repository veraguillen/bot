# app/api/webhook.py
"""
Módulo puente para mantener compatibilidad con importaciones existentes.
Este archivo reexporta el meta_router como webhook_router para mantener la compatibilidad
con el código existente que espera importar webhook_router desde este módulo.
"""

from .meta import meta_router

# Reexportar meta_router como webhook_router para compatibilidad
webhook_router = meta_router

# Exportar también las funciones relevantes para mayor compatibilidad
try:
    from .meta import (
        webhook_verification,
        receive_webhook_events,
        send_whatsapp_message
    )
except ImportError as e:
    from app.utils.logger import logger
    logger.warning(f"No se pudieron importar algunas funciones de meta.py: {str(e)}")
