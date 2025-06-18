# app/api/meta.py
# app/api/meta.py
import httpx
import json
import re
import os
import asyncio
from fastapi import APIRouter, HTTPException, Request, Response, status, BackgroundTasks, Query, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any
from ..core.database import get_db_session
from datetime import datetime, timezone, timedelta
from typing import Union, Dict, List, Any, Optional

from app.core.config import settings
from app.utils.logger import logger

# Crear instancia global de TokenManager al inicio
token_manager = None
http_client_meta = None

class TokenManager:
    def __init__(self):
        self.token: Optional[str] = None
        self.expiration: Optional[datetime] = None 
        self.phone_number_id: Optional[str] = None
        self.messenger_token: Optional[str] = None
        self.messenger_expiration: Optional[datetime] = None
        self._load_initial_tokens()

    def _load_initial_tokens(self):
        if not settings:
            logger.critical("TokenManager: Settings no disponibles al inicializar.")
            return
            
        # --- CORRECCIONES AQUÍ ---
        if settings.WHATSAPP_ACCESS_TOKEN: # Usar MAYÚSCULAS
            self.token = settings.WHATSAPP_ACCESS_TOKEN
            self.expiration = datetime.now(timezone.utc) + timedelta(hours=1) 
            logger.info(f"TokenManager: WhatsApp token inicial cargado desde settings. Validez asumida por ~1 hora.")
            logger.debug(f"TokenManager (inicial): WhatsApp token: '{self.token[:10] if self.token else 'N/A'}...', Len: {len(self.token) if self.token else 0}")
        else:
            logger.warning("TokenManager: WHATSAPP_ACCESS_TOKEN no encontrado en settings.")

        self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID # Usar MAYÚSCULAS
        if not self.phone_number_id:
            logger.warning("TokenManager: WHATSAPP_PHONE_NUMBER_ID no encontrado en settings.")

        if settings.MESSENGER_PAGE_ACCESS_TOKEN: # Usar MAYÚSCULAS
            self.messenger_token = settings.MESSENGER_PAGE_ACCESS_TOKEN
            self.messenger_expiration = datetime.now(timezone.utc) + timedelta(hours=1)
            logger.info("TokenManager: Messenger token inicial cargado desde settings.")
        else:
            logger.warning("TokenManager: MESSENGER_PAGE_ACCESS_TOKEN no encontrado en settings.")
        # --- FIN CORRECCIONES ---

    def get_whatsapp_token(self) -> Optional[str]:
        if not settings: 
            logger.error("TokenManager: get_whatsapp_token llamado pero settings no está disponible.")
            return None

        # --- CORRECCIONES AQUÍ ---
        if settings.WHATSAPP_ACCESS_TOKEN and self.token != settings.WHATSAPP_ACCESS_TOKEN:
            logger.info("TokenManager: WhatsApp token en settings ha cambiado, actualizando token interno.")
            self.token = settings.WHATSAPP_ACCESS_TOKEN
            self.expiration = datetime.now(timezone.utc) + timedelta(hours=1) 

        if self.token and self.expiration and datetime.now(timezone.utc) < self.expiration:
            logger.debug("TokenManager: Devolviendo token de WhatsApp existente y válido.")
            return self.token
        
        if self.token and self.expiration: # Expiró o está a punto de expirar
            logger.warning(f"TokenManager: Token de WhatsApp ha expirado (según lógica interna) o está ausente y settings lo tiene.")
            if settings.WHATSAPP_ACCESS_TOKEN:
                self.token = settings.WHATSAPP_ACCESS_TOKEN
                self.expiration = datetime.now(timezone.utc) + timedelta(hours=1)
                logger.info(f"TokenManager: Token de WhatsApp (re)cargado de settings.")
                return self.token
            else: 
                logger.error("TokenManager: Token de WhatsApp expirado y no se pudo recargar de settings (WHATSAPP_ACCESS_TOKEN no presente).")
                self.token = None 
                self.expiration = None
                return None
        
        if not self.token and settings.WHATSAPP_ACCESS_TOKEN:
            logger.info("TokenManager: Token interno era None, cargando de settings.")
            self.token = settings.WHATSAPP_ACCESS_TOKEN
            self.expiration = datetime.now(timezone.utc) + timedelta(hours=1)
            return self.token
        # --- FIN CORRECCIONES ---
            
        logger.error("TokenManager: No hay token de WhatsApp válido disponible y no se pudo obtener de settings.")
        return None

    def get_phone_number_id(self) -> Optional[str]:
        if not settings: return None
        # --- CORRECCIÓN AQUÍ ---
        if settings.WHATSAPP_PHONE_NUMBER_ID and self.phone_number_id != settings.WHATSAPP_PHONE_NUMBER_ID:
             self.phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
             logger.info(f"TokenManager: WHATSAPP_PHONE_NUMBER_ID actualizado/cargado desde settings: {self.phone_number_id}")
        # --- FIN CORRECCIÓN ---
        return self.phone_number_id

    def invalidate_whatsapp_token(self):
        logger.warning("TokenManager: Invalidando token de WhatsApp actual (probablemente debido a error 401/403 de API).")
        self.token = None
        self.expiration = None

    def get_messenger_token(self) -> Optional[str]:
        if not settings: return None
        # --- CORRECCIÓN AQUÍ ---
        if settings.MESSENGER_PAGE_ACCESS_TOKEN and self.messenger_token != settings.MESSENGER_PAGE_ACCESS_TOKEN:
            self.messenger_token = settings.MESSENGER_PAGE_ACCESS_TOKEN
            self.messenger_expiration = datetime.now(timezone.utc) + timedelta(hours=1)
        # --- FIN CORRECCIÓN ---
        
        if self.messenger_token and self.messenger_expiration and datetime.now(timezone.utc) < self.messenger_expiration:
            return self.messenger_token
        # ... (lógica de expiración y recarga para messenger token si es necesaria) ...
        logger.error("TokenManager: No hay token de Messenger válido disponible.")
        return None


# Inicializar el token_manager y preparación para el cliente HTTP
def init_meta_token_manager():
    global token_manager
    # Inicializar TokenManager
    token_manager = TokenManager()
    return token_manager

# Crear el cliente HTTP para Meta API (será llamado desde el ciclo de vida de la app)
def create_meta_client():
    """Crea y configura un cliente HTTP para la API de Meta.
    
    Este cliente debe ser gestionado mediante el ciclo de vida de la aplicación,
    creándolo al inicio y cerrándolo al apagado.
    
    Returns:
        httpx.AsyncClient: Cliente HTTP configurado para la API de Meta
    """
    # Configurar cliente HTTP para la API de Meta
    _BASE_URL_META_CLIENT = "https://graph.facebook.com"
    _HTTP_TIMEOUT_META_CLIENT = 30.0
    
    if settings and hasattr(settings, 'http_client_timeout'):
        _HTTP_TIMEOUT_META_CLIENT = float(settings.http_client_timeout)
    
    meta_client = httpx.AsyncClient(
        base_url=f"{_BASE_URL_META_CLIENT}/{settings.META_API_VERSION}",
        timeout=_HTTP_TIMEOUT_META_CLIENT,
        headers={"Content-Type": "application/json"}
    )
    
    logger.info(f"Cliente HTTP para Meta API creado. Base URL: {meta_client.base_url}")
    return meta_client

# Inicializar solo el token_manager al importar el módulo
# El cliente HTTP se inicializará en el lifespan de la app
if settings:
    init_meta_token_manager()
else:
    logger.warning("No se pudo inicializar el TokenManager: settings no disponible")


# Crear router para endpoints relacionados con Meta (WhatsApp/Messenger)
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status, BackgroundTasks

# Definimos el router para endpoints de Meta/WhatsApp
meta_router = APIRouter()

@meta_router.get("/webhook")
async def webhook_verification(request: Request,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token")):
    """Endpoint para verificar la autenticidad de un webhook de WhatsApp/Meta.
    Implementación según la documentación oficial de Meta:
    https://developers.facebook.com/docs/graph-api/webhooks/getting-started
    
    En modo SUBSCRIBE:
    - Meta envía un GET a este endpoint cuando se configura el webhook
    - Debemos verificar que hub.verify_token coincida con nuestro WHATSAPP_VERIFY_TOKEN
    - Si coincide, respondemos con el valor de hub.challenge
    
    Retorna:
        str: El valor del challenge enviado por Meta si la verificación es exitosa.
    """
    # Acceder al token de verificación desde la configuración centralizada (igual que en routes.py)
    if settings and hasattr(settings, 'WHATSAPP_VERIFY_TOKEN'):
        VERIFY_TOKEN = settings.WHATSAPP_VERIFY_TOKEN
    else:
        VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN") or settings.VERIFY_TOKEN if settings else None
        if not VERIFY_TOKEN:
            logger.error("CRÍTICO [meta.py]: No se pudo cargar WHATSAPP_VERIFY_TOKEN. La verificación del Webhook fallará.")
            raise HTTPException(status_code=500, detail="Error de configuración del servidor: Token de verificación no definido.")
    
    logger.info(f"META GET /webhook: Verificación recibida. Mode: '{hub_mode}', Token: '{hub_verify_token}', Challenge: '{hub_challenge}'")
    
    # Verificar token con validaciones más robustas
    if not hub_mode or not hub_verify_token:
        logger.warning(f"META GET /webhook: Verificación fallida. Faltan parámetros requeridos.")
        raise HTTPException(status_code=400, detail="Faltan parámetros requeridos para verificación.")
        
    if hub_mode == "subscribe" and hub_verify_token == VERIFY_TOKEN:
        if hub_challenge:
            logger.info(f"META GET /webhook: VERIFICACIÓN EXITOSA. Devolviendo Challenge: '{hub_challenge}'")
            return Response(content=hub_challenge, media_type="text/plain")
        else:
            logger.error("META GET /webhook: Verificación fallida. Falta 'hub.challenge' en la solicitud.")
            raise HTTPException(status_code=400, detail="Solicitud de verificación inválida: Falta 'hub.challenge'.")
    elif hub_mode == "subscribe":
        logger.warning(f"META GET /webhook: VERIFICACIÓN FALLIDA: Token inválido. Recibido: '{hub_verify_token}', Esperado: '****{VERIFY_TOKEN[-4:] if VERIFY_TOKEN else ''}')")
        raise HTTPException(status_code=403, detail="Token de verificación inválido.")
    else:
        logger.warning(f"META GET /webhook: VERIFICACIÓN FALLIDA: Modo incorrecto ('{hub_mode}').")
        raise HTTPException(status_code=400, detail="Modo o parámetros de verificación inválidos.")

@meta_router.post("/webhook")
async def receive_webhook_events(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db_session: AsyncSession = Depends(get_db_session)
):
    """
    Endpoint para recibir eventos de webhook de WhatsApp/Meta.
    
    Este endpoint responde inmediatamente con 200 OK y delega el procesamiento
    a una tarea en segundo plano para evitar timeouts y reintentos de Meta.
    """
    logger.info("META POST /webhook: Solicitud de mensaje entrante recibida.")
    
    try:
        # Leer el payload del request
        try:
            payload_dict = await request.json()
            # Loguear solo una parte del payload para no llenar los logs
            logger.debug(f"  Payload JSON recibido (preview): {json.dumps(payload_dict, indent=2, ensure_ascii=False)[:1000]}...")
        except json.JSONDecodeError as json_err:
            raw_body_content = "No se pudo leer el cuerpo crudo."
            try:
                raw_body_bytes = await request.body()
                raw_body_content = raw_body_bytes.decode(errors='replace')[:500] # Preview del cuerpo crudo
            except Exception as body_read_err:
                logger.debug(f"  Error adicional al intentar leer el cuerpo crudo: {body_read_err}")
            logger.error(f"Error al parsear JSON del webhook: {json_err}. Cuerpo crudo (preview): {raw_body_content}", exc_info=True)
            raise HTTPException(status_code=400, detail=f"Payload JSON inválido: {str(json_err)}")
        except Exception as e_read_req:
            logger.error(f"Error inesperado al obtener JSON del request: {e_read_req}", exc_info=True)
            raise HTTPException(status_code=400, detail="Error al leer el cuerpo de la solicitud.")

        # Validación básica del payload
        if not isinstance(payload_dict, dict) or 'object' not in payload_dict:
            logger.warning(f"Payload inválido recibido: {str(payload_dict)[:200]}...")
            # Aún así devolvemos 200 para evitar que Meta deshabilite el webhook
            return {"status": "success", "message": "Payload inválido, pero se aceptó para evitar reintentos."}

        # Añadir la tarea en segundo plano para procesar el payload
        from ..main.webhook_handler import process_webhook_payload_in_background
        background_tasks.add_task(
            process_webhook_payload_in_background,
            payload=payload_dict,
            request=request
        )
        
        logger.info("META POST /webhook: Payload aceptado y encolado para procesamiento en segundo plano.")
        
        # Responder inmediatamente con 200 OK para evitar reintentos de Meta
        return {
            "status": "accepted", 
            "message": "Evento de webhook recibido y encolado para procesamiento.",
            "processed_in_background": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException as http_exc:
        # Relanzar excepciones HTTP para que FastAPI las maneje
        logger.warning(f"META POST /webhook: HTTPException: {http_exc.detail}")
        raise http_exc
    except Exception as e_processing:
        # Capturar cualquier otro error inesperado
        error_id = f"err_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        logger.error(f"META POST /webhook [{error_id}]: Error inesperado: {e_processing}", exc_info=True)
        
        # CRÍTICO: Devolver 200 OK a Meta incluso con error interno para evitar que Meta deshabilite el webhook
        return {
            "status": "error",
            "error_id": error_id,
            "message": "Error interno del servidor, pero se aceptó la notificación.",
            "processed_in_background": False,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

async def send_whatsapp_message(
    to: str, 
    message_payload: Union[str, Dict[str, Any]],
    interactive_buttons: Optional[List[Dict[str, Any]]] = None,
    request: Optional[Request] = None
) -> Optional[Dict[str, Any]]:
    # Obtener el cliente HTTP desde el contexto actual
    http_client = None
    
    # Intentar obtener el cliente HTTP desde el request si está disponible
    if request and hasattr(request.app.state, 'meta_http_client'):
        http_client = request.app.state.meta_http_client
    
    # Si no tenemos request o el cliente no está en el estado, intentar obtenerlo desde contexto actual
    if http_client is None:
        # Intentar obtener el contexto actual si estamos en un endpoint FastAPI
        try:
            from fastapi import Request
            from starlette.concurrency import iterate_in_threadpool
            import inspect
            
            # Buscar el request en la pila de llamadas
            frame = inspect.currentframe()
            while frame:
                if 'request' in frame.f_locals and isinstance(frame.f_locals['request'], Request):
                    if hasattr(frame.f_locals['request'].app.state, 'meta_http_client'):
                        http_client = frame.f_locals['request'].app.state.meta_http_client
                        break
                frame = frame.f_back
        except Exception as e:
            logger.debug(f"No se pudo obtener el request actual: {e}")
    
    # Si después de todo no tenemos cliente, reportar error
    if http_client is None:
        logger.error("send_whatsapp_message: Cliente HTTP para Meta API no disponible. No se puede enviar mensaje.")
        return {"error": True, "status_code": "CLIENT_NOT_AVAILABLE", "details": "HTTP client for Meta not available."}

    access_token = token_manager.get_whatsapp_token()
    phone_number_id = token_manager.get_phone_number_id()
    
    if not access_token:
        logger.error("send_whatsapp_message: No se pudo obtener el token de acceso de WhatsApp.")
        return {"error": True, "status_code": "TOKEN_ERROR", "details": "Missing WhatsApp Access Token."}
    if not phone_number_id:
        logger.error("send_whatsapp_message: No se pudo obtener el WhatsApp Phone Number ID.")
        return {"error": True, "status_code": "CONFIG_ERROR", "details": "Missing WhatsApp Phone Number ID."}

    # Asegurar que el 'to' no tenga '+' u otros caracteres que Meta no espera para el WABA ID
    recipient_waid = re.sub(r'\D', '', to)  # Quita todo lo que no sea dígito
    
    # Usar la versión de la API desde la configuración del cliente HTTP
    # La URL base ya incluye la versión correcta
    url_path = f"/{phone_number_id}/messages"
    
    data_to_send: Dict[str, Any]

    if interactive_buttons and isinstance(interactive_buttons, list) and len(interactive_buttons) > 0:
        logger.info(f"Preparando mensaje interactivo con botones para {recipient_waid}")
        # ... (tu lógica de formateo de botones, que parece buena) ...
        api_buttons_formatted = []
        for btn_def in interactive_buttons:
            if isinstance(btn_def, dict) and btn_def.get("type") == "reply" and \
               isinstance(btn_def.get("reply"), dict) and \
               isinstance(btn_def["reply"].get("id"), str) and \
               isinstance(btn_def["reply"].get("title"), str):
                
                button_title = btn_def["reply"]["title"][:20] # Truncar a 20 chars
                button_id = btn_def["reply"]["id"][:256]     # Truncar a 256 chars
                api_buttons_formatted.append({"type": "reply", "reply": {"id": button_id, "title": button_title}})
            else:
                logger.error(f"Formato de botón interactivo no válido omitido: {btn_def}")

        if not api_buttons_formatted:
            logger.error(f"No se pudieron formatear botones válidos para {recipient_waid}. Intentando enviar como texto simple.")
            text_fallback = message_payload if isinstance(message_payload, str) else \
                            (message_payload.get("text", "Se produjo un error al mostrar las opciones.") if isinstance(message_payload, dict) else "Error.")
            # Evitar recursión infinita si message_payload es complejo y no string/dict con text
            if isinstance(text_fallback, str):
                return await send_whatsapp_message(to, text_fallback) 
            else:
                logger.error("Fallback a texto simple falló porque el payload no es string/dict con 'text'. No se envía mensaje.")
                return {"error": True, "status_code": "PAYLOAD_ERROR", "details": "Invalid payload for text fallback."}


        body_text_interactive = (message_payload if isinstance(message_payload, str) else
                                 message_payload.get("text", "Por favor, selecciona una opción:") if isinstance(message_payload, dict) else
                                 "Por favor, selecciona una opción:")

        data_to_send = {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": recipient_waid,
            "type": "interactive",
            "interactive": {"type": "button", "body": {"text": body_text_interactive},"action": {"buttons": api_buttons_formatted}}
        }
    else: 
        text_content_simple = (message_payload if isinstance(message_payload, str) else
                               message_payload.get("text") if isinstance(message_payload, dict) and "text" in message_payload else
                               str(message_payload)) # Fallback a convertir a string
        
        logger.info(f"Preparando mensaje de texto simple para {recipient_waid}: '{text_content_simple[:70]}...'")
        data_to_send = {
            "messaging_product": "whatsapp", "recipient_type": "individual", "to": recipient_waid,
            "type": "text", "text": {"preview_url": False, "body": text_content_simple}
        }

    logger.debug(f"Enviando POST a Meta API. Path con versión: {url_path}")
    logger.debug(f"Payload de WhatsApp a enviar: {json.dumps(data_to_send, ensure_ascii=False, indent=2)}")

    # Implementar reintentos para errores de red
    max_retries = 3
    retry_delay = 1  # segundos
    last_exception = None
    
    try:
        for attempt in range(1, max_retries + 1):
            try:
                # Intento de envío
                logger.debug(f"Intento {attempt}/{max_retries} de envío a Meta API")
                response = await http_client.post(url_path, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}, json=data_to_send)
                
                # Loguear siempre la respuesta de Meta, incluso si no es un error de status
                response_status = response.status_code
                response_content_text = "No se pudo leer contenido de respuesta."
                try:
                    response_content_bytes = await response.aread()
                    response_content_text = response_content_bytes.decode(errors='replace')
                except Exception as e_read_resp:
                    logger.warning(f"No se pudo leer/decodificar contenido de respuesta de Meta: {e_read_resp}")

                logger.debug(f"Respuesta de Meta API: Status={response_status}, Contenido (preview)='{response_content_text[:300]}...'")

                response.raise_for_status() # Lanza error para >= 400
                
                try:
                    response_data = json.loads(response_content_text) # Parsear el texto que ya leímos
                    logger.info(f"Mensaje de WhatsApp enviado exitosamente a {recipient_waid}. Respuesta de Meta (parseada): {response_data}")
                    return response_data
                except json.JSONDecodeError:
                    logger.error(f"Respuesta exitosa (status {response_status}) de Meta pero no es JSON válido: '{response_content_text}'")
                    return {"error": False, "status_code": response_status, "details": "Success status but invalid JSON response from Meta.", "raw_response": response_content_text}

            except httpx.HTTPStatusError as e_status:
                # El cuerpo del error ya fue logueado arriba si response_content_text se leyó
                logger.error(f"Error HTTP ({e_status.response.status_code}) al enviar mensaje de WhatsApp a {recipient_waid}. URL: {e_status.request.url}.")
                
                error_json_details = {}
                try:
                    # Intenta parsear response_content_text (que ya contiene el cuerpo del error)
                    error_json_details = json.loads(response_content_text) 
                except json.JSONDecodeError: # Si el cuerpo del error no es JSON
                    logger.warning("El cuerpo del error HTTP de Meta no es JSON válido.")
                    error_json_details = {"raw_error_body": response_content_text}
                
                # Chequeo específico para invalidar token
                error_code_from_meta = error_json_details.get("error", {}).get("code")
                if error_code_from_meta == 190: # Subcódigo para token inválido/expirado
                    logger.warning(f"Error de token de Meta (código {error_code_from_meta}). Invalidando token de WhatsApp.")
                    token_manager.invalidate_whatsapp_token()
                
                return {"error": True, "status_code": e_status.response.status_code, "details_dict": error_json_details, "raw_body": response_content_text}
            
            except httpx.RequestError as e_req: # Errores de red, DNS, etc.
                last_exception = e_req
                # Si no es el último intento, reintentamos
                if attempt < max_retries:
                    logger.warning(f"Error de red al enviar mensaje de WhatsApp a {recipient_waid} (intento {attempt}/{max_retries}): {e_req}. Reintentando en {retry_delay}s...")
                    await asyncio.sleep(retry_delay)
                    # Incrementar el delay para el próximo reintento (backoff exponencial)
                    retry_delay *= 2
                else:
                    # Si hemos agotado los reintentos, logueamos el error final
                    logger.error(f"Error de red al enviar mensaje de WhatsApp a {recipient_waid} después de {max_retries} intentos: {e_req}", exc_info=True)
                    return {"error": True, "status_code": "NETWORK_ERROR", "details": str(e_req), "attempts": max_retries}
    
    except Exception as e_general: # Cualquier otra excepción
        logger.error(f"Error inesperado al enviar mensaje de WhatsApp a {recipient_waid}: {e_general}", exc_info=True)
        return {"error": True, "status_code": "UNKNOWN_SEND_ERROR", "details": str(e_general)}


async def send_messenger_message(
    recipient_id: str,
    message_text: str,
    quick_replies: Optional[List[Dict[str, Any]]] = None,
    request: Optional[Request] = None
) -> Optional[Dict[str, Any]]:
    # Obtener el cliente HTTP desde el contexto actual
    http_client = None
    
    # Intentar obtener el cliente HTTP desde el request si está disponible
    if request and hasattr(request.app.state, 'meta_http_client'):
        http_client = request.app.state.meta_http_client
    
    # Si no tenemos request o el cliente no está en el estado, intentar obtenerlo desde contexto actual
    if http_client is None:
        # Intentar obtener el contexto actual si estamos en un endpoint FastAPI
        try:
            from fastapi import Request
            import inspect
            
            # Buscar el request en la pila de llamadas
            frame = inspect.currentframe()
            while frame:
                if 'request' in frame.f_locals and isinstance(frame.f_locals['request'], Request):
                    if hasattr(frame.f_locals['request'].app.state, 'meta_http_client'):
                        http_client = frame.f_locals['request'].app.state.meta_http_client
                        break
                frame = frame.f_back
        except Exception as e:
            logger.debug(f"No se pudo obtener el request actual: {e}")
    
    # Si después de todo no tenemos cliente, reportar error
    if http_client is None:
        logger.error("send_messenger_message: Cliente HTTP para Meta API no disponible.")
        return {"error": True, "status_code": "CLIENT_NOT_AVAILABLE", "details": "HTTP client for Meta not available."}
        
    # TODO: Completar implementación de envío a Messenger cuando se requiera
    # Actualmente esta es una implementación parcial para demostrar la inyección de dependencias
    logger.warning("send_messenger_message: Función no completamente implementada")
    return {"error": True, "status_code": "NOT_IMPLEMENTED"}