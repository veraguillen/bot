import httpx
import json
import inspect
import asyncio
import contextlib
from typing import Optional, List, Dict, Any, AsyncGenerator, Callable
from urllib.parse import urlparse # Para validación de URL

# Imports para circuit breaker y caché
from app.utils.resilience import async_circuit
from app.core.cache import llm_cache

# Imports para trazabilidad y observabilidad
from app.utils.logger import logger, get_request_id

# Intenta importar settings y logger
try:
    from app.core.config import settings
    SETTINGS_LOADED = True
except ImportError:
    import logging
    logger = logging.getLogger("app.api.llm_client_fallback")
    if not logger.hasHandlers():
        _h = logging.StreamHandler()
        _f = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
        _h.setFormatter(_f)
        logger.addHandler(_h)
        logger.setLevel(logging.INFO)
    logger.error("Error importando settings o logger principal. Usando fallback logger para llm_client.")
    settings = None # type: ignore
    SETTINGS_LOADED = False

# --- Constants ---
DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_LLM_TIMEOUT = 30.0  # Segundos
CHAT_COMPLETIONS_ENDPOINT_PATH = "/chat/completions" # Path relativo al base_url
MAX_CLIENT_CACHE_SIZE = 10  # Número máximo de clientes a mantener en caché
CLIENT_REUSE_MAX_REQUESTS = 50  # Número máximo de solicitudes para un cliente antes de reciclarlo

def _get_validated_base_url() -> str:
    """Obtiene y valida la URL base de OpenRouter desde la configuración."""
    if not SETTINGS_LOADED or not settings or not hasattr(settings, 'OPENROUTER_CHAT_ENDPOINT'):
        logger.warning(f"  OPENROUTER_CHAT_ENDPOINT no encontrado en settings. Usando URL base por defecto: {DEFAULT_OPENROUTER_BASE_URL}")
        return DEFAULT_OPENROUTER_BASE_URL
    
    # Convertir Pydantic HttpUrl a string si es necesario
    configured_url_str = str(settings.OPENROUTER_CHAT_ENDPOINT)
    
    # Intentar remover el path específico si está presente en la URL base configurada
    # La idea es que OPENROUTER_CHAT_ENDPOINT solo contenga la URL base.
    if CHAT_COMPLETIONS_ENDPOINT_PATH in configured_url_str:
        logger.warning(
            f"  OPENROUTER_CHAT_ENDPOINT ('{configured_url_str}') parece contener el path completo del endpoint. "
            f"Se intentará usar solo la parte base de la URL (antes de '{CHAT_COMPLETIONS_ENDPOINT_PATH}')."
        )
        base_url_candidate = configured_url_str.split(CHAT_COMPLETIONS_ENDPOINT_PATH)[0]
    else:
        base_url_candidate = configured_url_str
    
    # Validar el formato de la URL base resultante
    try:
        parsed = urlparse(base_url_candidate)
        if not all([parsed.scheme, parsed.netloc]): # Debe tener scheme (http/https) y netloc (dominio)
            raise ValueError(f"La URL base '{base_url_candidate}' es inválida (falta scheme o netloc).")
        logger.info(f"  URL base para OpenRouter validada: {base_url_candidate}")
        return base_url_candidate
    except ValueError as e_url: # Captura ValueError de urlparse o el nuestro
        logger.error(f"  Error validando la URL base '{base_url_candidate}': {e_url}. Usando URL por defecto: {DEFAULT_OPENROUTER_BASE_URL}")
        return DEFAULT_OPENROUTER_BASE_URL

# --- Client Initialization ---
# Eliminamos el singleton global en favor de inyección de dependencias

class LLMClientFactory:
    """
    Factory para gestionar la creación y ciclo de vida de clientes httpx.AsyncClient.
    Implementa patrón de pool con creación bajo demanda y cierre seguro.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Inicializa el estado del factory."""
        # Configuración básica
        self._config_loaded = False
        self._base_url = _get_validated_base_url()  # Inicializar directamente con la URL validada
        self._headers = None
        self._timeout = DEFAULT_LLM_TIMEOUT
        self._lock = asyncio.Lock()  # Lock para operaciones concurrentes
        
        # Pool de clientes con conteo de uso
        self._clients = {}  # Diccionario para clientes y su conteo de uso
        
        # Límites y configuración
        self.MAX_POOL_SIZE = 5
        # SOLUCIÓN PARA EVENT LOOP CLOSED:
        # Reducir drásticamente la reutilización de clientes para prevenir errores de ciclo de eventos
        # Cada cliente se usará como máximo 3 veces antes de ser reciclado
        self.MAX_CLIENT_USES = 3
        
        logger.debug("LLMClientFactory inicializado. Pool size: 0")
    
    async def _load_config(self):
        """
        Carga la configuración necesaria para los clientes.
        """
        if self._base_url is None:
            self._base_url = _get_validated_base_url()
            
        if self._headers is None and SETTINGS_LOADED and settings:
            self._headers = {
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json"
            }
            self._timeout = float(getattr(settings, 'LLM_HTTP_TIMEOUT', DEFAULT_LLM_TIMEOUT))
    
    async def get_client(self) -> httpx.AsyncClient:
        """
        Obtiene un cliente HTTP para OpenRouter.
        Crea un nuevo cliente si es necesario o reutiliza uno existente.
        Incluye el request_id en los headers si está disponible para mejorar la trazabilidad.
        
        Returns:
            httpx.AsyncClient: Cliente HTTP configurado para llamadas a OpenRouter
        """
        # Asegurar que tenemos la configuración cargada
        await self._load_config()
        
        # Verificar si tenemos la configuración necesaria
        if not self._base_url or not self._headers:
            raise RuntimeError("No se puede crear el cliente LLM: Configuración no cargada correctamente.")
        
        async with self._lock:
            # SOLUCIÓN PARA EVENT LOOP CLOSED: 
            # Limpiar clientes que han superado su límite de uso
            # usando nuestro propio límite de reutilización más estricto
            expired_clients = []
            for client_id, (client, request_count) in self._clients.items():
                if request_count >= self.MAX_CLIENT_USES:
                    expired_clients.append(client_id)
            
            # Cerrar clientes expirados
            for client_id in expired_clients:
                client, _ = self._clients.pop(client_id)
                try:
                    await client.aclose()
                    logger.debug(f"Cliente HTTP ID={client_id} cerrado por alcanzar límite de uso")
                except Exception as e:
                    logger.warning(f"Error al cerrar cliente HTTP ID={client_id}: {e}")
            
            # SOLUCIÓN PARA EVENT LOOP CLOSED:
            # Reducir el pool si excede el tamaño máximo definido en la clase
            if len(self._clients) > self.MAX_POOL_SIZE:
                oldest_clients = sorted(self._clients.items(), key=lambda x: x[1][1])[:-self.MAX_POOL_SIZE]
                for client_id, (client, _) in oldest_clients:
                    try:
                        await client.aclose()
                        logger.debug(f"Cliente HTTP ID={client_id} cerrado por exceder tamaño de pool")
                    except Exception as e:
                        logger.warning(f"Error al cerrar cliente HTTP ID={client_id}: {e}")
                    self._clients.pop(client_id)
            
            # Crear headers con el request_id si está disponible para trazabilidad
            # Copia los headers base
            headers = dict(self._headers) if self._headers else {}
            
            # Agregar X-Request-ID si hay un request_id activo en el contexto
            request_id = get_request_id()
            if request_id:
                # Incluir el request_id en los headers para correlación en sistemas externos
                headers['X-Request-ID'] = request_id
                logger.debug(f"Agregando X-Request-ID: {request_id} a cliente LLM HTTP")
            
            # Crear un nuevo cliente con los headers actualizados
            client = httpx.AsyncClient(
                base_url=self._base_url,
                headers=headers,
                timeout=self._timeout
            )
            
            client_id = id(client)
            self._clients[client_id] = (client, 0)
            
            log_msg = (
                f"Nuevo cliente HTTP ID={client_id} creado. "
                f"Base URL: '{self._base_url}', Timeout: {self._timeout}s, "
                f"Pool size: {len(self._clients)}"
            )
            if request_id:
                log_msg += f", Request-ID: {request_id}"
                
            logger.debug(log_msg)
            
            return client
    
    async def return_client(self, client):
        """
        Devuelve un cliente al pool, incrementando su contador de uso.
        Verifica si el ciclo de eventos asociado al cliente sigue siendo válido.
        
        Args:
            client: El cliente HTTP a devolver al pool
        """
        if not client:
            return
            
        client_id = id(client)
        
        # Verificar si el cliente tiene un ciclo de eventos válido antes de reutilizarlo
        client_valid = True
        try:
            # Intentar acceder al bucle del cliente para verificar que es válido
            if hasattr(client, '_transport') and hasattr(client._transport, '_pool'):
                if getattr(client._transport._pool, '_loop', None) is None:
                    logger.warning(f"Cliente HTTP ID={client_id} tiene ciclo de eventos nulo. Se cerrará.")
                    client_valid = False
                else:
                    try:
                        # Verificar si el ciclo de eventos está cerrado
                        loop = client._transport._pool._loop
                        if loop.is_closed():
                            logger.warning(f"Cliente HTTP ID={client_id} tiene ciclo de eventos cerrado. Se cerrará.")
                            client_valid = False
                    except Exception as e:
                        logger.warning(f"Error al verificar ciclo de eventos del cliente ID={client_id}: {e}")
                        client_valid = False
        except Exception as e:
            logger.warning(f"Error al acceder a los atributos internos del cliente HTTP ID={client_id}: {e}")
            # Por seguridad, considerarlo inválido
            client_valid = False
        
        async with self._lock:
            if client_id in self._clients and client_valid:
                _, request_count = self._clients[client_id]
                self._clients[client_id] = (client, request_count + 1)
                logger.debug(f"Cliente HTTP ID={client_id} devuelto al pool. Usos: {request_count + 1}/{self.MAX_CLIENT_USES}")
            else:
                # Si el cliente no está en nuestro registro o no es válido, lo cerramos
                try:
                    await client.aclose()
                    if not client_valid:
                        logger.debug(f"Cliente HTTP ID={client_id} cerrado por tener ciclo de eventos inválido")
                    else:
                        logger.debug(f"Cliente HTTP desconocido ID={client_id} cerrado")
                except Exception as e:
                    logger.warning(f"Error al cerrar cliente HTTP ID={client_id}: {e}")
                
                # Si estaba en nuestro registro pero era inválido, lo eliminamos
                if client_id in self._clients and not client_valid:
                    self._clients.pop(client_id)
    
    @contextlib.asynccontextmanager
    async def client_context(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """
        Contexto asíncrono que proporciona un cliente HTTP y lo devuelve al pool cuando termina.
        
        Usage:
            async with factory.client_context() as client:
                response = await client.post(...)
        
        Yields:
            httpx.AsyncClient: Cliente HTTP configurado con ciclo de eventos válido
        """
        client = None
        try:
            # SOLUCIÓN PARA EVENT LOOP CLOSED:
            # Verificar si tenemos un ciclo de eventos válido
            try:
                # Si esto falla, es que no hay un ciclo de eventos válido
                current_loop = asyncio.get_running_loop()
                loop_running = current_loop.is_running()
                logger.debug(f"LLM: Ciclo de eventos actual válido y {'corriendo' if loop_running else 'no corriendo'}")
            except RuntimeError:
                logger.warning("LLM: No hay ciclo de eventos válido, se usará un cliente totalmente nuevo")
            
            # Obtener cliente fresco para cada solicitud
            client = await self.get_client()
            yield client
        finally:
            if client:
                await self.return_client(client)
    
    async def close_all(self):
        """
        Cierra todos los clientes HTTP en el pool.
        """
        async with self._lock:
            for client_id, (client, _) in list(self._clients.items()):
                try:
                    await client.aclose()
                    logger.debug(f"Cliente HTTP ID={client_id} cerrado durante limpieza")
                except Exception as e:
                    logger.warning(f"Error al cerrar cliente HTTP ID={client_id}: {e}")
            self._clients.clear()

# Instancia global del factory
_llm_client_factory = None

def get_llm_client_factory() -> LLMClientFactory:
    """
    Obtiene la instancia global del factory de clientes HTTP.
    """
    global _llm_client_factory
    if _llm_client_factory is None:
        _llm_client_factory = LLMClientFactory()
    return _llm_client_factory


def create_llm_client() -> httpx.AsyncClient:
    """
    Crea una nueva instancia del cliente HTTP para OpenRouter.
    
    Returns:
        httpx.AsyncClient: Cliente HTTP configurado para hacer llamadas a la API de OpenRouter
    """
    if not SETTINGS_LOADED or not settings:
        raise RuntimeError("No se puede crear el cliente LLM: Configuración no cargada correctamente.")
    
    try:
        base_url = _get_validated_base_url()
        timeout = float(getattr(settings, 'LLM_HTTP_TIMEOUT', DEFAULT_LLM_TIMEOUT))
        
        # Configurar cabeceras para autenticación
        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Crear y configurar el cliente
        client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            timeout=timeout
        )
        
        logger.info(
            f"Cliente HTTP para LLM (OpenRouter) creado. "
            f"Base URL: '{base_url}', Timeout: {timeout}s"
        )
        
        return client
        
    except Exception as e:
        logger.critical(f"Error CRÍTICO al crear el cliente HTTP para LLM: {e}", exc_info=True)
        raise

# Función para generar respuesta de chat con sistema y usuario separados
@async_circuit
async def generate_chat_completion(
    system_message: str, 
    user_message: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    request: Optional[Any] = None
) -> str:
    """
    Genera una respuesta de chat usando mensajes de sistema y usuario separados.
    
    Args:
        system_message: El mensaje de sistema que establece el contexto y personalidad
        user_message: El mensaje del usuario con la consulta o instrucción
        temperature: Temperatura para la generación (opcional)
        max_tokens: Máximo de tokens en la respuesta (opcional)
        
    Returns:
        La respuesta generada por el LLM o un mensaje de error
    """
    logger.info(f"CHAT LLM: Generando respuesta para mensaje de usuario: '{user_message[:50]}...'")
    
    # Obtener configuración desde settings o usar valores por defecto
    openrouter_model_id = getattr(settings, "OPENROUTER_MODEL_CHAT", "meta-llama/llama-3-8b-instruct")
    llm_temp = temperature if temperature is not None else float(getattr(settings, 'LLM_TEMPERATURE', 0.7))
    llm_max_t = max_tokens if max_tokens is not None else int(getattr(settings, 'LLM_MAX_TOKENS', 1000))
    
    # Obtener cliente HTTP asíncrono
    client = http_client
    client_factory = get_llm_client_factory()
    client_from_context = False
    
    # Si no se proporcionó un cliente, intentar obtenerlo de diferentes fuentes
    if client is None:
        # 1. Intentar obtener del request si se proporcionó
        if request and hasattr(request, 'app') and hasattr(request.app, 'state') and hasattr(request.app.state, 'llm_http_client'):
            client = request.app.state.llm_http_client
            logger.debug("CHAT LLM: Cliente HTTP obtenido desde request.app.state")
        else:
            # 2. Intentar obtener del request actual a través de inspección de la pila de llamadas
            try:
                # Inspeccionamos la pila de llamadas para encontrar el objeto request de FastAPI
                for frame_info in inspect.stack():
                    frame = frame_info.frame
                    if 'request' in frame.f_locals:
                        potential_request = frame.f_locals['request']
                        if hasattr(potential_request, 'app') and hasattr(potential_request.app, 'state'):
                            if hasattr(potential_request.app.state, 'llm_http_client'):
                                client = potential_request.app.state.llm_http_client
                                logger.debug("CHAT LLM: Cliente HTTP obtenido desde request en pila de llamadas")
                                break
            except Exception as e:
                logger.warning(f"CHAT LLM: Error al buscar request en pila de llamadas: {e}")
            
            # 3. Si aún no tenemos cliente, usaremos el factory para crear uno nuevo
            if client is None:
                # No obtenemos el cliente inmediatamente, usaremos un contexto asíncrono más adelante
                logger.debug("CHAT LLM: Se usará el factory para crear un cliente HTTP")
                client_from_context = True
    
    # Preparar mensajes para la API
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": user_message}
    ]
    
    # Generar clave de caché basada en los mensajes
    cache_key = f"chat_{hash(json.dumps(messages))}"
    cached_response = llm_cache.get(cache_key)
    if cached_response:
        logger.info("CHAT LLM: Respuesta recuperada de caché")
        return cached_response
    
    logger.debug(f"CHAT LLM: Enviando solicitud a OpenRouter con {len(messages)} mensajes")
    
    # Preparar payload
    payload = {
        "model": openrouter_model_id,
        "messages": messages,
        "temperature": llm_temp,
        "max_tokens": llm_max_t,
        "stream": False
    }

    # AGREGAR LOGGING PARA DEBUG
    logger.info(f"CHAT LLM: Modelo que se enviará: '{openrouter_model_id}'")
    logger.info(f"CHAT LLM: Payload completo: {json.dumps(payload, ensure_ascii=False)}")

    try:
        # Obtener URL base desde settings o usar la predeterminada
        base_url = _get_validated_base_url()
        endpoint_url = f"{base_url}{CHAT_COMPLETIONS_ENDPOINT_PATH}"
        
        # Configurar cabeceras
        openrouter_api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
        if not openrouter_api_key:
            error_msg = "OPENROUTER_API_KEY no configurada en settings"
            logger.error(f"CHAT LLM: {error_msg}")
            return f"Error de configuración: {error_msg}"
            
        headers = {
            "Authorization": f"Bearer {openrouter_api_key}",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"CHAT LLM: Enviando solicitud a {endpoint_url} con payload: {json.dumps(payload, ensure_ascii=False)[:200]}...")
        
        # Realizar la petición HTTP con el cliente apropiado
        if client_from_context:
            # Usar el contexto asíncrono del factory para obtener un cliente seguro
            logger.debug("CHAT LLM: Usando contexto asíncrono del factory para llamada HTTP")
            async with client_factory.client_context() as safe_client:
                # CORRECCIÓN: Usar solo el path relativo ya que el cliente tiene base_url configurado
                response = await safe_client.post(CHAT_COMPLETIONS_ENDPOINT_PATH, json=payload, headers=headers)
        else:
            # Usar el cliente proporcionado o el obtenido del request
            logger.debug("CHAT LLM: Usando cliente HTTP proporcionado para llamada HTTP")
            if client is None:
                logger.error("CHAT LLM: Cliente HTTP es None, no se puede hacer la petición")
                return "Error interno: Cliente HTTP no disponible"
            # CORRECCIÓN: Usar solo el path relativo ya que el cliente tiene base_url configurado
            response = await client.post(CHAT_COMPLETIONS_ENDPOINT_PATH, json=payload, headers=headers)
        
        # Verificar código de estado
        if response.status_code != 200:
            # Verificar que response sea un objeto de respuesta válido
            if hasattr(response, 'text'):
                try:
                    error_text = response.text
                except Exception:
                    error_text = str(response) if response else "Respuesta inválida"
            else:
                error_text = str(response) if response else "Respuesta inválida"
            logger.error(f"CHAT LLM: Error HTTP {response.status_code}: {error_text[:200]}")
            return f"Error en el servicio de chat (código {response.status_code})"
            
        # Procesar respuesta exitosa
        response_data = response.json()
        logger.debug(f"CHAT LLM: Respuesta recibida: {json.dumps(response_data, ensure_ascii=False)[:500]}...")
        
        # Extraer y devolver la respuesta generada
        if 'choices' in response_data and len(response_data['choices']) > 0:
            response_text = response_data['choices'][0]['message']['content']
            # Guardar en caché
            llm_cache.set(cache_key, response_text)
            return response_text
        else:
            error_msg = f"Estructura de respuesta inesperada: {response_data}"
            logger.error(f"CHAT LLM: {error_msg}")
            return f"Error: Respuesta inesperada del servicio de chat"
            
    except httpx.HTTPStatusError as e:
        logger.error(f"  Error HTTP al comunicarse con OpenRouter: {e}", exc_info=True)
        return f"Error al comunicarse con el servicio LLM. Status: {e.response.status_code}, Respuesta: {e.response.text[:200] if hasattr(e, 'response') and hasattr(e.response, 'text') else 'No disponible'}"
    except httpx.ConnectError as e:
        logger.error(f"  Error de conexión con OpenRouter: {e}", exc_info=True)
        return "Error de conexión con el servicio LLM. Por favor, revisa tu conexión a internet y vuelve a intentarlo."
    except httpx.TimeoutException as e:
        logger.error(f"  Timeout al comunicarse con OpenRouter: {e}", exc_info=True)
        return "Tiempo de espera agotado para obtener respuesta del LLM. El servicio puede estar saturado, por favor intenta nuevamente en unos momentos."
    except asyncio.CancelledError:
        logger.warning("  Operación cancelada durante la comunicación con OpenRouter", exc_info=True)
        # Re-levantamos este error para que FastAPI pueda manejarlo correctamente
        raise
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            logger.error(f"  Error de ciclo de eventos cerrado en llamada LLM: {e}", exc_info=True)
            return "Error interno: Ciclo de eventos cerrado. Por favor, intenta nuevamente."
        else:
            logger.error(f"  RuntimeError al comunicarse con OpenRouter: {e}", exc_info=True)
            return f"Error interno al comunicarse con el servicio LLM: {str(e)[:200]}"
    except Exception as e:
        logger.error(f"  Error inesperado al comunicarse con OpenRouter: {e}", exc_info=True)
        return f"Error inesperado al comunicarse con el servicio LLM: {str(e)[:200]}"
    
    finally:
        # Ya no es necesario cerrar el cliente aquí, eso lo maneja el código que lo creó
        pass

@async_circuit
async def get_llm_response(
    prompt_from_builder: str,
    http_client: Optional[httpx.AsyncClient] = None,
    request = None
) -> Optional[str]:
    """
    Obtiene una respuesta de un modelo de lenguaje a través de OpenRouter.
    Implementa circuit breaker para proteger contra fallos en cascada y caché
    para mejorar el rendimiento y reducir costos.
    Incluye soporte para trazabilidad con request_id para correlacionar todas las operaciones.
    
    Devuelve el texto de la respuesta o un mensaje de error como string.
    """
    # Obtener el request_id del contexto actual para trazabilidad completa
    request_id = get_request_id()
    request_id_str = request_id if request_id else "sin-request-id"
    
    logger.debug(f"[{request_id_str}] get_llm_response: Iniciando. Preview del prompt recibido (primeros 200 chars): '{prompt_from_builder[:200]}...'")

    # SOLUCIÓN PARA EVENT LOOP CLOSED: SIEMPRE usar un nuevo cliente desde el factory
    # ignoramos cualquier cliente existente para evitar problemas con ciclos de eventos cerrados
    client_factory = get_llm_client_factory()
    
    # Si nos proporcionaron un cliente o hay uno en app.state, lo ignoramos
    # para evitar los errores "Event loop is closed"
    if http_client is not None:
        logger.debug("LLM: Ignorando cliente HTTP proporcionado para evitar errores de ciclo de eventos")
        
    # Si hay un cliente en request.app.state, lo registramos pero no lo usamos
    if request and hasattr(request, 'app') and hasattr(request.app, 'state') and hasattr(request.app.state, 'llm_http_client'):
        logger.debug("LLM: Ignorando cliente HTTP en app.state para evitar errores de ciclo de eventos")
    
    # Siempre vamos a usar el contexto asíncrono del factory
    # para garantizar un cliente con ciclo de eventos válido
    logger.debug("LLM: Se usará el factory para crear un cliente HTTP nuevo (prevenir Event loop is closed)")
    # Usaremos client_context más adelante en lugar de obtener un cliente ahora

    if not SETTINGS_LOADED or not settings:
        logger.error(f"[{request_id_str}] Error: Settings no disponibles. No se puede acceder a la configuración del LLM.")
        return "Error interno: Configuración de la aplicación no disponible."
        
    cache_key = llm_cache.key_for_prompt(prompt_from_builder)
    cached_response = llm_cache.get(cache_key)
    if cached_response:
        logger.info(f"[{request_id_str}] Respuesta recuperada de caché. Evitando llamada a OpenRouter.")
        return cached_response

    # Validar configuración esencial del LLM desde settings
    openrouter_api_key = getattr(settings, 'OPENROUTER_API_KEY', None)
    openrouter_model_id = getattr(settings, 'OPENROUTER_MODEL_CHAT', None)
    llm_temp = float(getattr(settings, 'LLM_TEMPERATURE', 0.2)) # Default a 0.7 si no está
    llm_max_t = int(getattr(settings, 'LLM_MAX_TOKENS', 200))    # Default a 512 si no está

    if not openrouter_api_key:
        logger.error(f"[{request_id_str}] Error: OPENROUTER_API_KEY no está configurada en settings.")
        return "Error interno: Clave API para OpenRouter no configurada."
    if not openrouter_model_id:
        logger.error(f"[{request_id_str}] Error: OPENROUTER_MODEL_CHAT (identificador del modelo) no está configurado en settings.")
        return "Error interno: Modelo de OpenRouter no configurado."

    # Headers recomendados por OpenRouter
    # !!! REEMPLAZA "https://tu-proyecto.com" con tu URL real o repo !!!
    site_url_for_header = getattr(settings, 'PROJECT_SITE_URL', "https://github.com/tu_usuario/tu_proyecto")
    site_url_str = str(site_url_for_header)  # Convertir HttpUrl a string
    app_name_for_header = getattr(settings, 'PROJECT_NAME', "ChatbotMultimarca")

    # Validar la API key antes de usarla
    if not openrouter_api_key or len(openrouter_api_key.strip()) < 20:
        logger.error(f"[{request_id_str}] Error CRÍTICO: API key de OpenRouter inválida o muy corta: '{openrouter_api_key[:5]}...' (longitud: {len(openrouter_api_key) if openrouter_api_key else 0})")
    else:
        logger.debug(f"[{request_id_str}] API key de OpenRouter parece válida con longitud: {len(openrouter_api_key)}")
        
    # Log del modelo que se usará
    logger.info(f"[{request_id_str}] Utilizando modelo: {openrouter_model_id} con temperatura {llm_temp} y max_tokens {llm_max_t}")
        
    # CORRECCIÓN: Ya no es necesario construir los headers aquí, ya están configurados en el cliente HTTP
    # El cliente HTTP fue creado con los headers correctos en create_llm_client() y es inyectado aquí
    # Esto evita duplicidad de headers que puede causar problemas

    # Preparar el payload de mensajes (system y user)
    system_content: str = ""
    user_content: str = prompt_from_builder.strip() # Por defecto, todo el prompt es del usuario

    # Intento de separar el prompt en "system" y "user" si los delimitadores están presentes
    # Esto es específico para cómo `rag_prompt_builder` estructura el prompt.
    # Asumimos que la parte "system" es todo ANTES de "**Pregunta del Usuario:**"
    # y la parte "user" es todo DESPUÉS de "**Pregunta del Usuario:**" y ANTES de "**Tu Respuesta como...**"
    
    system_marker_end = "**Pregunta del Usuario:**" # Lo que sigue es la pregunta del usuario
    user_marker_end = "**Tu Respuesta como" # Lo que sigue es donde el LLM debe empezar a escribir

    try:
        if system_marker_end in prompt_from_builder:
            parts = prompt_from_builder.split(system_marker_end, 1)
            system_content = parts[0].strip()
            
            # La parte del usuario está en parts[1], pero necesitamos quitar lo que viene después de la pregunta real.
            if len(parts) > 1 and parts[1]:
                user_part_full = parts[1].strip()
                if user_marker_end in user_part_full:
                    user_content = user_part_full.split(user_marker_end, 1)[0].strip()
                else:
                    user_content = user_part_full # Tomar todo si el marcador de respuesta no está
            else: # No debería pasar si system_marker_end está, pero por si acaso
                user_content = "" 
            
            logger.debug(f"  Prompt dividido: System content (len {len(system_content)}): '{system_content[:100]}...', User content (len {len(user_content)}): '{user_content[:100]}...'")
        else:
            logger.debug("  Delimitador para system content ('**Pregunta del Usuario:**') no encontrado. Todo el prompt se usará como 'user_content'.")
            # system_content ya es "" y user_content es prompt_from_builder.strip()
    except Exception as e_parse_prompt:
        logger.warning(f"  Advertencia: Ocurrió un error al intentar parsear el prompt para system/user: {e_parse_prompt}. Se usará el prompt completo como user_content.", exc_info=True)
        system_content = "" # Resetear por si acaso
        user_content = prompt_from_builder.strip()


    messages: List[Dict[str, str]] = []
    if system_content: # Solo añadir system message si tiene contenido
        messages.append({"role": "system", "content": system_content})
    
    if not user_content: # user_content no debería estar vacío después de la lógica anterior
        logger.error(f"  Error Crítico: El contenido del usuario (user_content) está vacío después del parseo. Prompt original (preview): '{prompt_from_builder[:100]}...'")
        return "Error interno: La pregunta del usuario resultó vacía después del procesamiento."
        
    messages.append({"role": "user", "content": user_content})

    payload = {
        "model": openrouter_model_id,
        "messages": messages,
        "max_tokens": llm_max_t,
        "temperature": llm_temp,
        "stream": False # No estamos usando streaming aquí
        # Puedes añadir otros parámetros como "top_p", "presence_penalty", etc. si es necesario
    }

    logger.info(f"  Enviando solicitud a OpenRouter. Modelo: '{openrouter_model_id}', Temp: {llm_temp}, MaxTokens: {llm_max_t}.")
    # Loguear el payload de mensajes es muy útil
    logger.debug(f"  Payload messages para OpenRouter: {json.dumps(messages, ensure_ascii=False, indent=2)}")
    # Loguear el payload completo (sin API key) también puede ser útil si se sospecha de otros parámetros
    payload_for_log = payload.copy() # No loguear la API Key si estuviera en el payload (no está aquí)
    logger.debug(f"  Payload completo para OpenRouter (sin API key implícita): {json.dumps(payload_for_log, ensure_ascii=False, indent=2)}")


    # Implementación de retry con backoff exponencial
    max_retries = 3  # Máximo 3 intentos en total (1 original + 2 reintentos)
    retry_count = 0
    last_exception = None
    response = None
    
    while retry_count < max_retries:
        try:
            # Log detallado antes de enviar la solicitud
            request_id_str = get_request_id() or "no-request-id"
            if retry_count == 0:
                logger.info(f"[{request_id_str}] Enviando solicitud a endpoint: {CHAT_COMPLETIONS_ENDPOINT_PATH}")
            else:
                logger.info(f"[{request_id_str}] Reintentando solicitud a OpenRouter (intento #{retry_count+1}/{max_retries}). Endpoint: {CHAT_COMPLETIONS_ENDPOINT_PATH}")
            
            # Usar el contexto asíncrono del factory para obtener un cliente seguro
            logger.debug(f"[{request_id_str}] LLM: Usando contexto asíncrono del factory para llamada HTTP")
            
            # Agregar metadata de request_id al payload para trazabilidad en OpenRouter
            if request_id_str and request_id_str != "no-request-id":
                # El campo user de OpenAI/OpenRouter se puede usar para tracking
                payload["user"] = f"req-{request_id_str}"
                
                # OpenRouter también acepta un campo de metadata personalizado
                if not payload.get("metadata"):
                    payload["metadata"] = {}
                payload["metadata"]["request_id"] = request_id_str
            
            async with client_factory.client_context() as safe_client:
                url_path = CHAT_COMPLETIONS_ENDPOINT_PATH
                logger.debug(f"[{request_id_str}] Enviando POST a {url_path} con {len(system_content)} chars en system y {len(user_content)} chars en user")
                response = await safe_client.post(
                    url_path,
                    json=payload,
                )
                
                # Log de trazabilidad con request_id
                logger.debug(f"[{request_id_str}] POST a {url_path} completado. Status: {response.status_code}")
                if response.status_code == 200:
                    logger.info(f"[{request_id_str}] Llamada al LLM exitosa")
                else:
                    logger.warning(f"[{request_id_str}] Llamada al LLM devolvió status code {response.status_code}")
            
            # Si llegamos aquí, la respuesta fue exitosa
            response.raise_for_status()  # Lanza HTTPStatusError si status >= 400
            break
                
        except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.RequestError) as e:
            last_exception = e
            retry_count += 1
            
            # Si es el último intento, no esperar y propagar la excepción
            if retry_count >= max_retries:
                logger.error(f"[{request_id_str}] Agotados todos los intentos ({max_retries}) de comunicación con OpenRouter. Último error: {e}")
                # La excepción será manejada por los bloques except específicos más adelante
                raise e
            
            # Backoff exponencial: 1s, 2s, 4s...
            wait_time = 2 ** (retry_count - 1)  # 1s en primer retry, 2s en segundo, etc.
            logger.warning(f"[{request_id_str}] Error en solicitud a OpenRouter (intento {retry_count}/{max_retries}): {e}. Reintentando en {wait_time}s...")
            await asyncio.sleep(wait_time)
    
    try:
        # Procesar la respuesta
        response_data = response.json()
        # logger.debug(f"  Respuesta JSON completa de OpenRouter: {json.dumps(response_data, ensure_ascii=False, indent=2)}") # Loguear JSON completo puede ser muy verboso

        # Extraer el contenido del mensaje de la respuesta
        if response_data.get("choices") and isinstance(response_data["choices"], list) and len(response_data["choices"]) > 0:
            first_choice = response_data["choices"][0]
            if isinstance(first_choice, dict) and first_choice.get("message") and \
               isinstance(first_choice["message"], dict) and "content" in first_choice["message"] and \
               isinstance(first_choice["message"]["content"], str):
                
                ai_response_text = first_choice["message"]["content"].strip()
                finish_reason = first_choice.get("finish_reason", "N/A")
                logger.info(f"  Respuesta de OpenRouter procesada exitosamente. Finish reason: '{finish_reason}'. Respuesta (preview): '{ai_response_text[:150]}...'")
                
                # Almacenar la respuesta en caché si fue exitosa
                cache_result = llm_cache.set(cache_key, ai_response_text)
                if cache_result:
                    logger.debug("  Respuesta almacenada en caché correctamente")
                else:
                    logger.warning("  No se pudo almacenar la respuesta en caché")
                
                # Aquí podrías añadir lógica para manejar diferentes finish_reasons si es necesario
                if finish_reason == "length":
                    logger.warning("  Respuesta truncada por max_tokens.")
                
                return ai_response_text
            else:
                logger.warning(f"  Estructura inesperada en 'choices[0].message' o 'content' en la respuesta de OpenRouter. Choice[0]: {first_choice}")
        else:
            logger.warning(f"  La respuesta de OpenRouter no contiene 'choices' válidas o la lista está vacía. Respuesta Data: {response_data}")
            
            # Si no se pudo extraer la respuesta por estructura inesperada
            return "Error: El modelo LLM no generó una respuesta con el formato esperado."
            
    except httpx.HTTPStatusError as e_status:
        error_body_text = "No se pudo leer el cuerpo del error HTTP."
        try:
            # Intentar leer el cuerpo de la respuesta de error de forma asíncrona
            error_response_content = await e_status.response.aread()
            error_body_text = error_response_content.decode(errors='replace') # Decodificar bytes a string
        except Exception as e_read_body:
            logger.error(f"  Error adicional al intentar leer el cuerpo de la respuesta de error HTTP de OpenRouter: {e_read_body}")
        
        logger.error(
            f"  Error HTTP de OpenRouter: Status Code {e_status.response.status_code}. "
            f"URL: {e_status.request.url}. "
            f"Cuerpo de la Respuesta de Error (preview): {error_body_text[:500]}...", # Loguear solo una preview
            exc_info=False # El traceback de HTTPStatusError no es tan útil como el cuerpo del error
        )
        # Devolver un mensaje de error más informativo al usuario/sistema
        return f"Error de comunicación con el servicio LLM (código {e_status.response.status_code}). Por favor, revisa los logs para más detalles."
    
    except httpx.TimeoutException as e_timeout:
        logger.error(f"  Timeout al llamar a OpenRouter. URL: {e_timeout.request.url if e_timeout.request else 'N/A'}. Error: {e_timeout}", exc_info=True)
        # Esta excepción será capturada por el circuit breaker
        raise ValueError("Error: La solicitud al servicio LLM excedió el tiempo de espera.")
    
    except httpx.RequestError as e_req: # Otros errores de red (DNS, conexión rechazada, etc.)
        logger.error(f"  Error de red/solicitud al llamar a OpenRouter. URL: {e_req.request.url if e_req.request else 'N/A'}. Error: {e_req}", exc_info=True)
        # Esta excepción será capturada por el circuit breaker
        raise ValueError("Error de red al contactar el servicio LLM. Verifica tu conexión y la disponibilidad del servicio.")
    
    except json.JSONDecodeError as e_json:
        # Esto podría pasar si la respuesta no es JSON válido a pesar de un status 200
        status_code = getattr(response, 'status_code', 'N/A') if 'response' in locals() else 'N/A'
        logger.error(f"  Error al decodificar la respuesta JSON de OpenRouter. Status: {status_code}. Error: {e_json}", exc_info=True)
        # logger.debug(f"   Contenido que falló la decodificación JSON: {response.text if 'response' in locals() else 'N/A'}")
        return "Error: La respuesta del servicio LLM no pudo ser interpretada (formato JSON inválido)."

    except RuntimeError as e_runtime:
        if "Event loop is closed" in str(e_runtime):
            logger.error(f"  Error de ciclo de eventos cerrado detectado en get_llm_response: {e_runtime}", exc_info=True)
            return "Error interno: Ciclo de eventos cerrado durante la comunicación con LLM. Por favor, intenta nuevamente."
        else:
            logger.error(f"  RuntimeError en get_llm_response: {e_runtime}", exc_info=True)
            return f"Error interno del servicio LLM: {str(e_runtime)[:200]}"
            
    except asyncio.CancelledError:
        logger.warning("  Operación cancelada durante la comunicación con OpenRouter", exc_info=True)
        # Re-levantamos este error para que FastAPI pueda manejarlo correctamente
        raise
        
    except Exception as e_unexpected: # Captura cualquier otra excepción no prevista
        logger.error(f"  Error inesperado y no manejado en get_llm_response (OpenRouter): {e_unexpected}", exc_info=True)
        return f"Error inesperado al comunicarse con el servicio LLM: {str(e_unexpected)[:200]}"