# Ejemplo de integración completa de request_id en llamadas al LLM
from typing import Optional, Dict, Any
import httpx
import json

from app.utils.logger import logger, get_request_id
from app.api.llm_client import get_llm_client_factory


async def enhanced_llm_call(
    prompt: str,
    http_client: Optional[httpx.AsyncClient] = None,
    request = None
) -> Dict[str, Any]:
    """
    Ejemplo de función mejorada para llamadas al LLM con integración completa de request_id
    para trazabilidad de extremo a extremo.
    
    Args:
        prompt: El prompt a enviar al LLM
        http_client: Cliente HTTP opcional para reutilizar
        request: Objeto request opcional para obtener información contextual
        
    Returns:
        Dict con la respuesta del LLM y metadatos
    """
    # Obtener request_id del contexto para correlacionar todas las operaciones
    request_id = get_request_id() or "no-request-id"
    
    # Logs iniciales con request_id para trazabilidad
    logger.info(f"[{request_id}] Iniciando llamada al LLM con prompt de {len(prompt)} caracteres")
    logger.debug(f"[{request_id}] Preview del prompt: '{prompt[:100]}...'")
    
    # Preparar el cliente HTTP con request_id en headers para propagación
    client_factory = get_llm_client_factory()
    
    # Crear payload con request_id para trazabilidad en APIs externas
    payload = {
        "prompt": prompt,
        "user": f"req-{request_id}",  # Campo estándar de OpenAI/OpenRouter para tracking
        "metadata": {
            "request_id": request_id  # Campo personalizado para sistemas propios
        }
    }
    
    # Ejecutar la llamada al LLM con trazabilidad
    try:
        # Usar el client_context asegura un cliente HTTP con ciclo de eventos válido
        # y con headers que incluyen X-Request-ID si está disponible
        async with client_factory.client_context() as client:
            # Log de la operación HTTP
            logger.debug(f"[{request_id}] Enviando solicitud HTTP al LLM")
            
            # Realizar la llamada HTTP
            response = await client.post("/endpoint", json=payload)
            
            # Log del resultado con request_id
            logger.info(f"[{request_id}] Respuesta del LLM recibida. Status: {response.status_code}")
            
            # Procesar y devolver resultado
            if response.status_code == 200:
                result = response.json()
                logger.debug(f"[{request_id}] Procesamiento exitoso de respuesta LLM")
                return {
                    "content": result.get("choices", [{}])[0].get("message", {}).get("content", ""),
                    "model": result.get("model", "unknown"),
                    "metadata": {
                        "request_id": request_id,
                        "status": "success"
                    }
                }
            else:
                logger.error(f"[{request_id}] Error en llamada al LLM. Status: {response.status_code}")
                error_content = await response.text()
                logger.error(f"[{request_id}] Detalle del error: {error_content[:500]}")
                return {
                    "content": f"Error al obtener respuesta (código {response.status_code})",
                    "metadata": {
                        "request_id": request_id,
                        "status": "error",
                        "error_code": response.status_code
                    }
                }
                
    except Exception as e:
        # Capturar y loguear cualquier error con request_id para trazabilidad
        logger.error(f"[{request_id}] Excepción en llamada al LLM: {str(e)}", exc_info=True)
        return {
            "content": f"Error de comunicación: {str(e)}",
            "metadata": {
                "request_id": request_id,
                "status": "exception",
                "error_type": type(e).__name__
            }
        }


# Ejemplo de integración en una función de webhook o endpoint FastAPI
async def process_user_message(user_message: str, request):
    """
    Ejemplo de función que procesa un mensaje de usuario y llama al LLM
    integrando request_id para trazabilidad completa.
    
    El request_id ya está disponible en el contexto gracias al middleware
    RequestIdMiddleware que lo establece al inicio de cada solicitud HTTP.
    """
    request_id = get_request_id()
    logger.info(f"[{request_id}] Procesando mensaje: '{user_message[:50]}...'")
    
    # Construir prompt
    prompt = f"Usuario pregunta: {user_message}\nResponde a esta pregunta de forma concisa."
    
    # Llamar al LLM con propagación implícita del request_id
    llm_response = await enhanced_llm_call(prompt, request=request)
    
    # Procesar la respuesta manteniendo la trazabilidad
    logger.info(f"[{request_id}] Respuesta del LLM procesada. Status: {llm_response['metadata']['status']}")
    
    # Devolver respuesta al usuario
    return {
        "message": llm_response["content"],
        "request_id": request_id  # Se puede devolver en la respuesta HTTP para correlación frontend
    }
