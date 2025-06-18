# app/__init__.py
import sys
import os
import logging 
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from datetime import datetime, timezone

# Información de diagnóstico para despliegue en contenedor
print(f"[INIT] Cargando app/__init__.py desde: {os.path.dirname(os.path.abspath(__file__))}")
print(f"[INIT] Directorio de trabajo: {os.getcwd()}")
print(f"[INIT] Python path: {sys.path}")

# --- 1. Carga de Configuración (settings) ---
try:
    from app.core.config import settings
    if settings is None: 
        raise RuntimeError("La instancia 'settings' es None después de importar desde app.core.config.")
    CONFIG_LOADED_SUCCESSFULLY = True
    # Usar print aquí es más seguro antes de que el logger principal esté configurado
    print(f"DEBUG PRINT [app/__init__.py]: 'settings' importado. PROJECT_NAME: {getattr(settings, 'PROJECT_NAME', 'ERROR AL LEER SETTINGS')}")
except Exception as e_cfg_init:
    emergency_logger_init = logging.getLogger("APP_INIT_SETTINGS_FAILURE")
    if not emergency_logger_init.hasHandlers():
        _h_emerg = logging.StreamHandler(sys.stderr)
        _f_emerg = logging.Formatter('%(asctime)s - %(name)s - CRITICAL - [%(filename)s:%(lineno)d] - %(message)s')
        _h_emerg.setFormatter(_f_emerg); emergency_logger_init.addHandler(_h_emerg); emergency_logger_init.setLevel(logging.CRITICAL)
    emergency_logger_init.critical(f"FALLO CRÍTICO AL CARGAR 'settings' EN app/__init__.py: {e_cfg_init}", exc_info=True)
    print(f"ERROR CRÍTICO [app/__init__.py]: Falló la importación/creación de 'settings': {e_cfg_init}", file=sys.stderr)
    settings = None 
    CONFIG_LOADED_SUCCESSFULLY = False
    sys.exit("Error crítico: Fallo al cargar la configuración. La aplicación no puede continuar.")

# --- 2. Configuración del Logger Principal de la Aplicación ---
logger: logging.Logger 
if CONFIG_LOADED_SUCCESSFULLY and settings:
    try:
        # REFACTOR: El logger ahora se auto-configura al importarlo
        from app.utils.logger import logger as main_app_logger, set_request_id, get_request_id, clear_request_id
        logger = main_app_logger 
        logger.info(f"Logger principal '{logger.name}' configurado automáticamente. Nivel efectivo: {logging.getLevelName(logger.getEffectiveLevel())}.")
    except Exception as e_logger_setup:
        logger_fallback_init = logging.getLogger("APP_INIT_LOGGER_SETUP_FALLBACK")
        if not logger_fallback_init.hasHandlers():
            _h_log_fall = logging.StreamHandler(sys.stdout)
            _f_log_fall = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
            _h_log_fall.setFormatter(_f_log_fall); logger_fallback_init.addHandler(_h_log_fall); logger_fallback_init.setLevel(logging.INFO)
        logger = logger_fallback_init
        logger.error(f"Error importando el logger principal: {e_logger_setup}. Usando logger de fallback.", exc_info=True)
else:
    logger = logging.getLogger("APP_INIT_NO_SETTINGS_FOR_LOGGER")
    if not logger.hasHandlers():
        _h_no_set = logging.StreamHandler(sys.stdout)
        _f_no_set = logging.Formatter('%(asctime)s - %(name)s - CRITICAL - [%(filename)s:%(lineno)d] - %(message)s')
        _h_no_set.setFormatter(_f_no_set); logger.addHandler(_h_no_set); logger.setLevel(logging.CRITICAL)
    logger.critical("Settings no disponibles, el logger principal no pudo ser configurado con settings.")

# --- 3. Resto de Importaciones y Definición de la App ---
# Importar módulos que podrían usar 'logger' o 'settings' DESPUÉS de que estén listos.
# from .core import database as db_module # Importar el módulo completo para el chequeo de AsyncSessionLocal
from .core.database import initialize_database, close_database_engine, AsyncSessionLocal # Importar AsyncSessionLocal para el chequeo
from .ai.rag_retriever import load_rag_components, verify_vector_db_access, LANGCHAIN_OK
from .api.llm_client import create_llm_client  # Importar la función para crear el cliente LLM
from .main.routes import router as main_routes_router
# from .api import router as general_api_router # Comentado para simplificar arranque

@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    logger.info(f"{'='*10} LIFESPAN: Iniciando Aplicación FastAPI {'='*10}")
    app_instance.state.db_ready = False
    app_instance.state.retriever = None
    app_instance.state.is_rag_ready = False
    app_instance.state.llm_http_client = None  # Inicializar el cliente HTTP del LLM como None

    if settings:
        logger.info("LIFESPAN: Intentando inicializar la base de datos...")
        try:
            db_ok = await initialize_database()
            # Verificar AsyncSessionLocal DESPUÉS de llamar a initialize_database
            # Importar database de nuevo aquí para asegurar que vemos la variable global actualizada
            from .core import database as db_module_lifespan 
            if db_ok and db_module_lifespan.AsyncSessionLocal is not None:
                app_instance.state.is_db_ready = True
                logger.info("LIFESPAN: Base de datos inicializada y db_module_lifespan.AsyncSessionLocal está configurado.")
            elif db_ok and db_module_lifespan.AsyncSessionLocal is None:
                app_instance.state.is_db_ready = False
                logger.critical("LIFESPAN CRITICAL POST-DB-INIT: db_module_lifespan.AsyncSessionLocal SIGUE SIENDO None!")
            else:
                app_instance.state.is_db_ready = False
                logger.error("LIFESPAN: FALLO en inicialización de BD (initialize_database devolvió False).")
        except Exception as e_db:
            app_instance.state.is_db_ready = False
            logger.critical(f"LIFESPAN: EXCEPCIÓN CRÍTICA durante initialize_database: {e_db}", exc_info=True)

        if LANGCHAIN_OK:
            logger.info("LIFESPAN: Intentando cargar componentes RAG con PGVector...")
            try:
                # Obtenemos el engine ya inicializado a través de la función de acceso
                from .core.database import get_db_engine
                db_engine = get_db_engine()
                
                if not db_engine:
                    raise RuntimeError("Motor de base de datos no disponible, imposible inicializar RAG")
                
                # Inicializar el sistema RAG pasando el engine asíncrono y obteniendo el retriever
                retriever = await load_rag_components(db_engine=db_engine)
                
                # Guardar el retriever en el estado de la aplicación para usarlo en los endpoints
                app_instance.state.retriever = retriever
                logger.info("LIFESPAN: Retriever guardado en el estado de la aplicación")
                
                # Verificar acceso a la base de datos vectorial
                logger.info("LIFESPAN: Verificando acceso a PGVector...")
                verification_result = await verify_vector_db_access()
                
                # Actualizar estado basado en el resultado de verificación
                if verification_result and verification_result.get("success") == True:
                    app_instance.state.is_rag_ready = True
                    logger.info(f"LIFESPAN: Componentes RAG con PGVector inicializados correctamente: {verification_result.get('message', '')}")
                else:
                    app_instance.state.is_rag_ready = False
                    error_msg = verification_result.get('error', 'Sin detalles') if verification_result else "Verificación fallida"
                    logger.warning(f"LIFESPAN: Verificación de PGVector fallida: {error_msg}")
            except Exception as e_rag:
                app_instance.state.is_rag_ready = False
                logger.error(f"LIFESPAN: EXCEPCIÓN al inicializar sistema RAG con PGVector: {e_rag}", exc_info=True)
        else:
            logger.warning("LIFESPAN: Langchain no disponible. Componentes RAG no se cargarán.")
            app_instance.state.is_rag_ready = False
    else:
        logger.critical("LIFESPAN: 'settings' no está disponible. Saltando inicialización de DB y RAG.")

    ready_msg = f"DB Lista: {app_instance.state.is_db_ready}, RAG Listo: {app_instance.state.is_rag_ready}"
    # Inicializar el cliente HTTP del LLM si no está en modo de solo lectura
    if not getattr(settings, 'LLM_READ_ONLY_MODE', False):
        try:
            # Importar y configurar el factory de clientes LLM
            from app.api.llm_client import get_llm_client_factory, create_llm_client
            logger.info("LIFESPAN: Inicializando factory de clientes HTTP para LLM...")
            llm_factory = get_llm_client_factory()
            
            # Crear un cliente inicial para verificar que el factory funciona
            logger.info("LIFESPAN: Inicializando cliente HTTP para LLM...")
            app_instance.state.llm_http_client = create_llm_client()
            logger.info("LIFESPAN: Cliente HTTP para LLM inicializado correctamente")
            
            # Almacenar el factory en el estado de la aplicación
            app_instance.state.llm_client_factory = llm_factory
            logger.info("LIFESPAN: Factory de clientes LLM configurado correctamente")
        except Exception as e:
            logger.error(f"LIFESPAN: Error al inicializar el cliente HTTP para LLM: {e}", exc_info=True)
            app_instance.state.llm_http_client = None
            app_instance.state.llm_client_factory = None
    else:
        logger.info("LIFESPAN: Modo solo lectura activado, omitiendo inicialización del cliente LLM")
        app_instance.state.llm_http_client = None
        app_instance.state.llm_client_factory = None
    
    # Inicializar el cliente HTTP para Meta API (WhatsApp/Messenger)
    try:
        from app.api.meta import create_meta_client
        logger.info("LIFESPAN: Inicializando cliente HTTP para Meta API...")
        app_instance.state.meta_http_client = create_meta_client()
        logger.info("LIFESPAN: Cliente HTTP para Meta API inicializado correctamente")
    except Exception as e:
        logger.error(f"LIFESPAN: Error al inicializar el cliente HTTP para Meta API: {e}", exc_info=True)
        app_instance.state.meta_http_client = None

    logger.info(f"{'='*10} LIFESPAN: Aplicación Lista para servir ({ready_msg}) {'='*10}")
    
    yield  # La aplicación está en ejecución
    
    # Fase de limpieza
    logger.info(f"{'='*10} LIFESPAN: Apagando Aplicación FastAPI {'='*10}")
    
    # Función auxiliar para cerrar clientes HTTP de forma segura
    async def close_http_client_safely(client, client_name):
        if client is None:
            return
            
        try:
            logger.info(f"LIFESPAN: Cerrando cliente HTTP para {client_name}...")
            
            try:
                # Intentar cierre asíncrono con timeout
                await asyncio.wait_for(client.aclose(), timeout=2.0)
                logger.info(f"LIFESPAN: Cliente HTTP para {client_name} cerrado correctamente (asíncrono)")
            except (asyncio.TimeoutError, RuntimeError, asyncio.CancelledError):
                # Fallback a cierre sincrónico
                logger.info(f"LIFESPAN: Cayendo en cierre sincrónico para {client_name}")
                client.close()
                logger.info(f"LIFESPAN: Cliente HTTP para {client_name} cerrado correctamente (sincrónico)")
        except Exception as e:
            logger.error(f"LIFESPAN: Error al cerrar el cliente HTTP para {client_name}: {e}", exc_info=True)
    
    # Cerrar todos los clientes HTTP del LLM a través del factory si existe
    if hasattr(app_instance.state, 'llm_client_factory') and app_instance.state.llm_client_factory is not None:
        try:
            logger.info("LIFESPAN: Cerrando todos los clientes HTTP del factory LLM...")
            await app_instance.state.llm_client_factory.close_all()
            logger.info("LIFESPAN: Todos los clientes HTTP del factory LLM cerrados correctamente")
        except Exception as e:
            logger.error(f"LIFESPAN: Error al cerrar clientes HTTP del factory LLM: {e}", exc_info=True)
        app_instance.state.llm_client_factory = None
    
    # Cerrar el cliente HTTP principal del LLM si existe
    if hasattr(app_instance.state, 'llm_http_client') and app_instance.state.llm_http_client is not None:
        client = app_instance.state.llm_http_client
        app_instance.state.llm_http_client = None  # Eliminar referencia primero
        await close_http_client_safely(client, "LLM principal")
        
    # Cerrar el cliente HTTP de Meta API si existe
    if hasattr(app_instance.state, 'meta_http_client') and app_instance.state.meta_http_client is not None:
        client = app_instance.state.meta_http_client
        app_instance.state.meta_http_client = None  # Eliminar referencia primero
        await close_http_client_safely(client, "Meta API")
    
    # Cerrar la conexión a la base de datos si está activa
    if app_instance.state.is_db_ready and callable(close_database_engine):
        try: 
            await close_database_engine()
            logger.info("LIFESPAN: Conexión a la base de datos cerrada")
        except Exception as e: 
            logger.error(f"LIFESPAN: Excepción en close_database_engine: {e}", exc_info=True)
    
    # Limpiar otros recursos
    app_instance.state.retriever = None 
    app_instance.state.llm_http_client = None
    
    logger.info("LIFESPAN: Recursos limpiados. Apagado completado.")

# --- Creación de la Instancia FastAPI ---
if not (CONFIG_LOADED_SUCCESSFULLY and settings):
    logger.critical("FALLO CATASTRÓFICO: No se puede crear instancia FastAPI, 'settings' no disponible.")
    app = None # type: ignore 
else:
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        lifespan=lifespan
    )
    from fastapi.middleware.cors import CORSMiddleware
    
    # Middleware de observabilidad con request_id para trazabilidad
    from app.utils.middleware import RequestIdMiddleware
    app.add_middleware(RequestIdMiddleware)
    logger.info("Middleware de observabilidad RequestIdMiddleware agregado a la aplicación")
    
    # Middleware de Cross-Origin Resource Sharing (CORS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"], # Restringir a métodos necesarios
        allow_headers=["*"]
    )
    logger.info("Middleware CORS agregado a la aplicación")
    
    # Bloques de diagnóstico para importaciones
    try:
        from app.api.meta import meta_router
        print("[INIT DIAGNÓSTICO] meta_router importado correctamente.")
    except ImportError as e:
        print(f"[INIT ERROR] Error importando meta_router: {e}")
        raise
        
    try:
        print("[INIT DIAGNÓSTICO] Intentando importar webhook_router...")
        from app.api.webhook import webhook_router
        print("[INIT DIAGNÓSTICO] webhook_router importado correctamente.")
    except ImportError as e:
        print(f"[INIT ERROR] Error importando webhook_router: {e}")
        raise
        
    try:
        print("[INIT DIAGNÓSTICO] Intentando importar rag_router...")
        from app.api.rag import rag_router
        print("[INIT DIAGNÓSTICO] rag_router importado correctamente.")
    except ImportError as e:
        print(f"[INIT ERROR] Error importando rag_router: {e}")
        raise
        
    try:
        print("[INIT DIAGNÓSTICO] Intentando importar health_router...")
        from app.api.health import health_router
        print("[INIT DIAGNÓSTICO] health_router importado correctamente.")
    except ImportError as e:
        print(f"[INIT ERROR] Error importando health_router: {e}")
        raise
        
    try:
        print("[INIT DIAGNÓSTICO] Intentando importar chat_router...")
        from app.api.chat import chat_router
        print("[INIT DIAGNÓSTICO] chat_router importado correctamente.")
    except ImportError as e:
        print(f"[INIT ERROR] Error importando chat_router: {e}")
        raise
    
    # Incluir routers en la aplicación
    try:
        print("[INIT DIAGNÓSTICO] Incluyendo routers en la aplicación...")
        
        # Incluir el router principal (contiene las rutas de las páginas legales)
        from app.main import main_router
        app.include_router(main_router)
        
        # Incluir los demás routers de la API
        app.include_router(meta_router)
        app.include_router(webhook_router)
        app.include_router(rag_router)
        app.include_router(health_router, prefix="/api")
        app.include_router(chat_router)
        
        logger.info("Routers incluidos correctamente (main, meta, webhook, rag, health, chat).")
    except Exception as e_router_final:
        logger.critical(f"Error al incluir routers en la instancia FastAPI: {e_router_final}", exc_info=True)

    @app.get("/", tags=["Status"], include_in_schema=False)
    async def root_status_endpoint(request: Request):
        db_s = getattr(request.app.state, 'is_db_ready', "desconocido")
        rag_s = getattr(request.app.state, 'is_rag_ready', "desconocido")
        logger.debug("Acceso a endpoint raíz '/' para estado.")
        return {
            "project": settings.PROJECT_NAME, "version": settings.PROJECT_VERSION,
            "status_message": "Servicio Activo",
            "database_status": "lista" if db_s is True else "no_lista" if db_s is False else db_s,
            "rag_status": "listo" if rag_s is True else "no_listo" if rag_s is False else rag_s,
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }
    logger.info(f"Instancia FastAPI '{settings.PROJECT_NAME}' v{settings.PROJECT_VERSION} creada y configurada. LOG_LEVEL app: {settings.LOG_LEVEL}.")
    # Información adicional sobre la estructura de archivos para diagnóstico
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__))
        logger.info(f"Estructura de directorios de la aplicación - Directorio app: {app_dir}")
        logger.info(f"Archivos en el directorio raíz: {os.listdir(os.path.dirname(app_dir))}")
        logger.info(f"Archivos en el directorio app: {os.listdir(app_dir)}")
    except Exception as e_diag:
        logger.warning(f"No se pudo obtener información de diagnóstico: {e_diag}")


if app is None and __name__ == "__main__":
    print("ERROR CRÍTICO: La instancia 'app' de FastAPI es None. No se puede iniciar.", file=sys.stderr)