"""
Middleware utilities for enhancing observability and request tracing.
Includes middleware for request ID tracking and other cross-cutting concerns.
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from typing import Callable, Optional
import uuid

from app.utils.logger import logger, set_request_id, get_request_id, clear_request_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware que asigna automáticamente un identificador único a cada solicitud HTTP.
    
    Mejora la observabilidad y trazabilidad al mantener un ID consistente
    a lo largo de toda la ejecución de la solicitud, facilitando la correlación
    de logs y eventos distribuidos.
    """
    
    def __init__(self, app):
        super().__init__(app)
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Captura cada solicitud, asigna un request_id y lo propaga en los headers de respuesta.
        
        Args:
            request: La solicitud HTTP entrante
            call_next: La función para continuar la cadena de middleware
            
        Returns:
            La respuesta HTTP con el request_id incluido
        """
        # Extraer request_id de los headers si existe, o generar uno nuevo
        request_id = request.headers.get("X-Request-ID")
        if request_id:
            # Usar el ID proporcionado por el cliente
            set_request_id(request_id)
            logger.debug(f"Usando request_id proporcionado por el cliente: {request_id}")
        else:
            # Generar ID único para esta solicitud
            request_id = set_request_id()
            logger.debug(f"Generado nuevo request_id: {request_id}")
        
        try:
            # Procesar la solicitud con el request_id establecido en el contexto
            response = await call_next(request)
            
            # Agregar el request_id a los headers de respuesta para correlación
            response.headers["X-Request-ID"] = request_id
            
            # Registrar información sobre la solicitud completada
            status_code = getattr(response, "status_code", 0)
            path = request.url.path
            method = request.method
            
            # Registrar estadísticas básicas de la solicitud
            if 400 <= status_code < 500:
                logger.warning(f"Cliente {method} {path} → {status_code}")
            elif status_code >= 500:
                logger.error(f"Error servidor {method} {path} → {status_code}")
            else:
                if path != "/health" and path != "/metrics":  # No registrar endpoints de healthcheck
                    logger.info(f"Completado {method} {path} → {status_code}")
            
            return response
            
        except Exception as e:
            # Capturar y registrar cualquier excepción no manejada
            logger.exception(f"Error no manejado procesando {request.method} {request.url.path}: {str(e)}")
            raise
        finally:
            # Siempre limpiar el request_id del contexto al finalizar
            clear_request_id()
