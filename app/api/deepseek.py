# app/api/deepseek.py
# Configurado para usar la API de DeepSeek directamente.

import httpx
from app.core.config import settings # Importar la instancia de settings
from app.utils.logger import logger # Asumiendo que tienes un logger centralizado
from typing import Optional, List, Dict, Any

# --- Configuración del Cliente HTTP para DeepSeek ---

_BASE_URL_DEEPSEEK = "https://api.deepseek.com/v1" # Base de la API de DeepSeek
if settings and hasattr(settings, 'deepseek_chat_endpoint'):
    # Si deepseek_chat_endpoint es la URL completa (ej. ".../chat/completions")
    # entonces el cliente debe configurarse con esa URL completa y el post debe ser a ""
    # Si deepseek_chat_endpoint es solo la base (ej. "https://api.deepseek.com/v1")
    # entonces el post debe ser a "/chat/completions"
    # Vamos a asumir que settings.deepseek_chat_endpoint es la URL COMPLETA del endpoint de chat.
    if "chat/completions" in settings.deepseek_chat_endpoint:
        _ACTUAL_ENDPOINT_DEEPSEEK = settings.deepseek_chat_endpoint
        _POST_PATH_DEEPSEEK = "" # La base_url ya es el endpoint completo
    else: # Si solo es la base de la API
        _ACTUAL_ENDPOINT_DEEPSEEK = settings.deepseek_chat_endpoint # Debería ser "https://api.deepseek.com/v1"
        _POST_PATH_DEEPSEEK = "/chat/completions" # El path específico para chat
else:
    # Fallback si settings no está o no tiene deepseek_chat_endpoint
    logger.warning("deepseek_chat_endpoint no encontrado en settings. Usando defaults.")
    _ACTUAL_ENDPOINT_DEEPSEEK = "https://api.deepseek.com/v1/chat/completions"
    _POST_PATH_DEEPSEEK = ""


_TIMEOUT_LLM = 30.0 # Fallback
if settings and hasattr(settings, 'http_client_timeout'):
    _TIMEOUT_LLM = settings.http_client_timeout

# Crear el cliente httpx para DeepSeek
try:
    client = httpx.AsyncClient(
        base_url=_ACTUAL_ENDPOINT_DEEPSEEK, # Usar el endpoint completo calculado
        timeout=_TIMEOUT_LLM
    )
    logger.info(f"Cliente HTTP para DeepSeek inicializado. Base URL (Endpoint): {_ACTUAL_ENDPOINT_DEEPSEEK}, Timeout: {_TIMEOUT_LLM}s")
except Exception as e_client:
    logger.error(f"Error al inicializar el cliente HTTP para DeepSeek: {e_client}", exc_info=True)
    client = None


async def get_deepseek_response(prompt_from_builder: str) -> Optional[str]:
    """
    Obtiene una respuesta de un modelo de lenguaje a través de la API de DeepSeek.
    """
    if client is None:
        logger.error("El cliente HTTP para DeepSeek no está inicializado.")
        return "Error interno: Cliente LLM no disponible."

    if not settings:
        logger.error("Settings no disponibles. No se puede acceder a la configuración de DeepSeek.")
        return "Error interno: Configuración no disponible."

    # Validar que las configuraciones necesarias de DeepSeek estén presentes
    if not settings.deepseek_api_key:
        logger.error("DEEPSEEK_API_KEY no está configurada en settings.")
        return "Error interno: Clave API para DeepSeek no configurada."
    if not settings.deepseek_model_chat:
        logger.error("DEEPSEEK_MODEL_CHAT no está configurado en settings.")
        return "Error interno: Modelo de DeepSeek no configurado."

    api_key = settings.deepseek_api_key
    model_identifier = settings.deepseek_model_chat # Debería ser "deepseek-chat" según tu .env
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    system_content: str = ""
    user_content: str = prompt_from_builder 
    try:
        if "**Pregunta Usuario:**" in prompt_from_builder:
            parts = prompt_from_builder.split("**Pregunta Usuario:**", 1)
            system_content = parts[0].strip() 
            user_content = parts[1].strip()
            if "**Respuesta:**" in user_content:
                user_content = user_content.split("**Respuesta:**", 1)[0].strip()
        else:
            logger.debug("Delimitador '**Pregunta Usuario:**' no encontrado. Todo el prompt como 'user_content'.")
    except Exception as e_parse:
        logger.warning(f"Error parseando prompt para system/user: {e_parse}. Usando prompt completo como user_content.")
        system_content = "" 
        user_content = prompt_from_builder

    messages: List[Dict[str, str]] = []
    if system_content:
        messages.append({"role": "system", "content": system_content})
    
    if not user_content or not user_content.strip():
        logger.error(f"User content vacío. Prompt original: '{prompt_from_builder[:100]}...'")
        return "Error interno: Pregunta del usuario vacía."
        
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": model_identifier,
        "messages": messages,
        "max_tokens": settings.deepseek_max_tokens,
        "temperature": settings.deepseek_temperature,
        "stream": False
    }

    logger.info(f"Enviando solicitud a DeepSeek. Modelo: {model_identifier}, Endpoint efectivo: {_ACTUAL_ENDPOINT_DEEPSEEK}")
    logger.debug(f"Path para POST: '{_POST_PATH_DEEPSEEK}'")
    logger.debug(f"Payload messages para DeepSeek: {messages}")
    logger.debug(f"Payload completo (sin API key): {payload}")

    try:
        # Si _ACTUAL_ENDPOINT_DEEPSEEK ya es la URL completa, _POST_PATH_DEEPSEEK será ""
        response = await client.post(url=_POST_PATH_DEEPSEEK, headers=headers, json=payload)
        
        response.raise_for_status() 
        
        data = response.json()
        logger.debug(f"Respuesta completa de DeepSeek (JSON): {data}")

        if data.get("choices") and isinstance(data["choices"], list) and len(data["choices"]) > 0:
            choice = data["choices"][0]
            if isinstance(choice, dict) and choice.get("message") and isinstance(choice["message"], dict) and \
               "content" in choice["message"] and isinstance(choice["message"]["content"], str):
                
                ai_message = choice["message"]["content"].strip()
                logger.info(f"Respuesta de DeepSeek recibida (primeros 100 chars): '{ai_message[:100]}...'")
                return ai_message
            else:
                logger.warning(f"Estructura inesperada en 'message' o 'content' en DeepSeek: {choice}")
        else:
            logger.warning(f"Respuesta de DeepSeek no contiene 'choices' válidas: {data}")
        return "Modelo no generó respuesta válida."

    except httpx.HTTPStatusError as e_status:
        error_body = "No se pudo leer cuerpo del error."
        try:
            error_body_bytes = await e_status.response.aread()
            error_body = error_body_bytes.decode(errors='replace')
        except Exception as read_err:
            logger.error(f"Error adicional leyendo cuerpo de error HTTP de DeepSeek: {read_err}")
        logger.error(f"Error HTTP de DeepSeek: {e_status.response.status_code} - URL: {e_status.request.url} - Cuerpo: {error_body}", exc_info=False)
        return f"Error de comunicación con DeepSeek ({e_status.response.status_code}). Detalles: {error_body[:200]}"
    except httpx.RequestError as e_req:
        logger.error(f"Error de red/solicitud llamando a DeepSeek: {e_req} - URL: {e_req.request.url}", exc_info=True)
        return "Error de red contactando DeepSeek."
    except Exception as e_unexpected:
        logger.error(f"Error inesperado en get_deepseek_response (DeepSeek): {e_unexpected}", exc_info=True)
        return "Error inesperado procesando respuesta de DeepSeek."