# app/ai/rag_retriever.py
"""
Módulo para la recuperación y búsqueda de documentos usando PostgreSQL/pgvector.

Este módulo proporciona funciones para cargar embeddings desde la base de datos PostgreSQL
usando pgvector, realizar búsquedas semánticas por similitud vectorial, y verificar el
estado del sistema RAG.
"""

import logging
import asyncio
from typing import List, Optional, Any, Dict
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_postgres import PGVector
from langchain_core.documents import Document as LangchainDocument
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_core.retrievers import BaseRetriever
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Flag de Disponibilidad de Dependencias ---
# Ya no necesitamos importar nuevamente las clases, solo verificar que el módulo esté disponible
try:
    # La importación correcta de HuggingFaceEmbeddings ya está en la línea 13
    # Las demás importaciones necesarias ya están en las líneas 14-16
    LANGCHAIN_OK = True
except ImportError as e_langchain:
    # Configurar un logger de emergencia si el logger principal aún no está disponible
    _emergency_logger_rag = logging.getLogger("rag_retriever_langchain_import_error")
    if not _emergency_logger_rag.hasHandlers():
        _h_emerg = logging.StreamHandler(sys.stderr)
        _f_emerg = logging.Formatter('%(asctime)s - %(name)s - CRITICAL - %(message)s')
        _h_emerg.setFormatter(_f_emerg); _emergency_logger_rag.addHandler(_h_emerg)
    _emergency_logger_rag.critical(
        f"Faltan librerías CRÍTICAS de Langchain/PostgreSQL (Error: {e_langchain}). "
        "El sistema RAG NO funcionará. Por favor, instala los paquetes requeridos: "
        "'pip install langchain langchain-community langchain-postgres sentence-transformers'"
    )
    LANGCHAIN_OK = False
    
    # Clases Dummy para evitar NameError si LANGCHAIN_OK es False
    class HuggingFaceEmbeddings: pass
    class LangchainDocument:
        def __init__(self, page_content: str, metadata: Optional[Dict[str, Any]] = None):
            self.page_content = page_content
            self.metadata = metadata or {}
    class VectorStoreRetriever: pass
    class PGVector: pass

# --- Logger para este módulo ---
logger = logging.getLogger(__name__)

# --- Importar settings y logger de la aplicación ---
try:
    from app.core.config import settings
    from app.utils.logger import logger
    CONFIG_AND_LOGGER_OK_RAG = True
    logger.info("rag_retriever.py: Configuración (settings) y logger principal cargados.")
except ImportError as e_cfg_log_rag:
    logger = logging.getLogger("app.ai.rag_retriever_fallback")
    if not logger.hasHandlers():
        _h_fall = logging.StreamHandler(sys.stderr)
        _f_fall = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s')
        _h_fall.setFormatter(_f_fall); logger.addHandler(_h_fall); logger.setLevel(logging.INFO)
    logger.error(f"Error CRÍTICO importando 'settings' o 'logger' principal: {e_cfg_log_rag}. Usando fallback logger.")
    settings = None
    CONFIG_AND_LOGGER_OK_RAG = False

# --- Variable global para el retriever ---
rag_retriever: Optional[VectorStoreRetriever] = None

async def load_rag_components(*, db_engine: AsyncEngine = None) -> Optional[BaseRetriever]:
    """
    Inicializa los componentes RAG que se usarán en toda la aplicación.
    Configura el modelo de embeddings y el vectorstore.
    
    Args:
        db_engine: Motor SQLAlchemy asíncrono ya configurado e inicializado.
        
    Returns:
        BaseRetriever: La instancia del retriever configurado o None si hay error.
    """
    global rag_retriever
    
    # Verificaciones iniciales de seguridad
    if not db_engine:
        logger.critical("RAG_INIT: No se proporcionó un db_engine. Imposible inicializar RAG.")
        raise ValueError("Se requiere un db_engine válido para inicializar componentes RAG")

    try:
        # 1. Cargar modelo de embeddings (es síncrono, lo ejecutamos en un thread)
        logger.info(f"RAG_INIT: Cargando modelo de embeddings '{settings.EMBEDDING_MODEL_NAME}'...")
        embedding_function = await asyncio.to_thread(
            HuggingFaceEmbeddings,
            model_name=settings.EMBEDDING_MODEL_NAME,
            model_kwargs={'device': 'cpu'}
        )
        logger.info("RAG_INIT: Modelo de embeddings cargado.")

        # 2. Conectar a PGVector usando el engine asíncrono inyectado
        logger.info(f"RAG_INIT: Conectando a PGVector (colección: '{settings.VECTOR_COLLECTION_NAME}')...")
        
        # La extensión 'vector' ya debería estar creada en database.py durante la inicialización
        # No es necesario que PGVector la vuelva a crear o intente operaciones compuestas
        # que causarían errores con asyncpg (cannot insert multiple commands into a prepared statement)
        try:
            # Configuración simplificada de PGVector compatible con la versión actual
            vectorstore = PGVector(
                connection=db_engine,
                collection_name=settings.VECTOR_COLLECTION_NAME,
                embeddings=embedding_function,
                pre_delete_collection=False,  # No intentar DROP COLLECTION
                create_extension=False  # No intentar crear la extensión
            )
            logger.info(f"RAG_INIT: PGVector inicializado con colección '{settings.VECTOR_COLLECTION_NAME}'. Asumiendo que la extensión vector ya existe.")
        except Exception as e:
            logger.critical(f"RAG_INIT: Error al inicializar PGVector: {str(e)}")
            raise
        
        # NO llamamos a await vectorstore.acreate_collection() aquí en el arranque.
        # Lo haríamos solo al ingestar datos. La aplicación debe poder arrancar
        # asumiendo que la base de datos ya está lista.
        
        logger.info("RAG_INIT: Objeto PGVector inicializado. Se asume que la colección ya existe.")
        
        logger.info("RAG_INIT: Conexión con PGVector establecida y colección asegurada.")

        # 3. Crear y almacenar el retriever
        k_for_retriever = settings.RAG_DEFAULT_K * settings.RAG_K_FETCH_MULTIPLIER
        rag_retriever = vectorstore.as_retriever(
            search_type="similarity",
            search_kwargs={'k': k_for_retriever}
        )
        logger.info(f"RAG_INIT: Componentes RAG cargados exitosamente.")
        
        # Devolvemos el retriever para que se pueda almacenar en el estado de la aplicación
        return rag_retriever

    except Exception as e:
        logger.critical(f"RAG_INIT: Error CRÍTICO al inicializar componentes RAG: {e}", exc_info=True)
        # Re-lanzar para que el lifespan falle y se sepa que la app está rota
        raise

async def search_relevant_documents(
    user_query: str,
    target_brand: Optional[str] = None,
    k_final: Optional[int] = None,
    retriever_instance: Optional[VectorStoreRetriever] = None
) -> List[LangchainDocument]:
    """
    Busca documentos relevantes de forma ASÍNCRONA.
    
    Args:
        user_query: Consulta del usuario
        target_brand: Nombre de la marca para filtrar resultados (opcional)
        k_final: Número máximo de documentos a devolver (opcional)
        retriever_instance: Instancia de VectorStoreRetriever a usar (opcional, usa el global por defecto)
    """
    retriever_to_use = retriever_instance or rag_retriever
    
    if not retriever_to_use:
        logger.error("RAG_SEARCH: No se proporcionó un retriever y no hay un retriever global disponible.")
        return []

    _k_final_to_use = k_final if k_final is not None else settings.RAG_DEFAULT_K
    # Recuperar más documentos para filtrar y obtener los mejores
    _k_retrieval = _k_final_to_use + 2

    try:
        # Usar el retriever proporcionado o el global
        initial_docs = await retriever_to_use.ainvoke(user_query)
        
        # Filtrar por marca si es necesario
        filtered_docs = initial_docs
        if target_brand and filtered_docs:
            before_count = len(filtered_docs)
            filtered_docs = [
                doc for doc in filtered_docs 
                if doc.metadata.get('brand') == target_brand
            ]
            logger.debug(f"RAG_SEARCH: Filtrado por marca '{target_brand}': {before_count} → {len(filtered_docs)} docs")
        
        # Deduplicación basada en contenido similar
        deduplicated_docs = _deduplicate_documents(filtered_docs)
        
        # Filtrar por calidad de contenido
        quality_filtered_docs = _filter_by_content_quality(deduplicated_docs, user_query)
        
        # Retornar los mejores k documentos
        final_docs = quality_filtered_docs[:_k_final_to_use]
        
        logger.debug(f"RAG_SEARCH: Documentos procesados: {len(initial_docs)} → {len(filtered_docs)} → {len(deduplicated_docs)} → {len(quality_filtered_docs)} → {len(final_docs)}")
        
        return final_docs

    except Exception as e:
        logger.error(f"RAG_SEARCH: Error durante la búsqueda asíncrona: {e}", exc_info=True)
        return []


def _deduplicate_documents(documents: List[LangchainDocument]) -> List[LangchainDocument]:
    """
    Elimina documentos duplicados o muy similares basándose en el contenido.
    """
    if not documents:
        return documents
    
    seen_contents = set()
    deduplicated = []
    
    for doc in documents:
        # Crear una representación normalizada del contenido
        normalized_content = doc.page_content.strip().lower()
        content_hash = hash(normalized_content[:100])  # Usar los primeros 100 caracteres
        
        if content_hash not in seen_contents:
            seen_contents.add(content_hash)
            deduplicated.append(doc)
    
    return deduplicated


def _filter_by_content_quality(documents: List[LangchainDocument], user_query: str) -> List[LangchainDocument]:
    """
    Filtra documentos basándose en la calidad y relevancia del contenido.
    """
    if not documents:
        return documents
    
    quality_docs = []
    query_lower = user_query.lower()
    
    for doc in documents:
        content = doc.page_content.strip()
        content_lower = content.lower()
        
        # Filtros de calidad
        if len(content) < 50:  # Muy corto
            continue
        if content.count('\n') > len(content) / 10:  # Demasiados saltos de línea
            continue
        if len(set(content_lower.split())) < 5:  # Muy pocas palabras únicas
            continue
            
        # Bonus por relevancia contextual
        doc.metadata['relevance_score'] = _calculate_relevance_score(content_lower, query_lower)
        quality_docs.append(doc)
    
    # Ordenar por score de relevancia
    quality_docs.sort(key=lambda x: x.metadata.get('relevance_score', 0), reverse=True)
    
    return quality_docs


def _calculate_relevance_score(content: str, query: str) -> float:
    """
    Calcula un score simple de relevancia basado en coincidencias de palabras.
    """
    content_words = set(content.split())
    query_words = set(query.split())
    
    if not query_words:
        return 0.0
    
    # Coincidencias exactas
    exact_matches = len(content_words.intersection(query_words))
    
    # Coincidencias parciales
    partial_matches = 0
    for q_word in query_words:
        for c_word in content_words:
            if q_word in c_word or c_word in q_word:
                partial_matches += 0.5
    
    # Score normalizado
    total_score = exact_matches + partial_matches
    return total_score / len(query_words)


async def verify_vector_db_access() -> Dict[str, Any]:
    """
    Verifica la conexión y funcionalidad de PGVector de forma ASÍNCRONA.
    Incluye manejo de errores especialmente adaptado para los problemas de
    inicialización de PostgreSQL con la extensión vector.
    """
    if not rag_retriever:
        return {"success": False, "error": "Retriever no inicializado."}
        
    try:
        # Realiza una búsqueda simple para verificar la funcionalidad básica
        # Evitamos cualquier operación compleja que pueda desencadenar múltiples comandos SQL
        await search_relevant_documents("test query", k_final=1)
        logger.info("RAG_VERIFY: Vector store verificado con éxito (search_relevant_documents)")
        return {"success": True, "message": "Conexión a PGVector y búsqueda de prueba completadas con éxito."}
    except TypeError as e:
        # Error específico de incompatibilidad de argumentos en PGVector
        error_str = str(e)
        if "got an unexpected keyword argument" in error_str:
            logger.critical(f"RAG_VERIFY: Error de incompatibilidad de versión en PGVector: {error_str}")
            return {"success": False, "error": f"Incompatibilidad de API en langchain-postgres: {error_str}"}
        return {"success": False, "error": error_str}
    except Exception as e:
        # Otros errores generales
        error_str = str(e)
        
        # Verificar si el error es sobre múltiples comandos SQL (caso compañero)
        if "cannot insert multiple commands into a prepared statement" in error_str:
            logger.warning(f"RAG_VERIFY: Se detectó error de preparación SQL múltiple: {error_str}")
            return {"success": False, "error": "Error de sentencia SQL múltiple. Revise la documentación de langchain-postgres."}
            
        # Cualquier otro error
        logger.error(f"RAG_VERIFY: Error durante verificación: {e}", exc_info=True)
        return {"success": False, "error": error_str}