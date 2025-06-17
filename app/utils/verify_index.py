import sys
from pathlib import Path
import logging
import asyncio
from typing import Dict, Any, List # Añadido List

# --- Ajuste de Rutas para Importar Configuración y Módulos de la App ---
# Asumiendo que este script está en /ruta/al/proyecto/app/utils/verify_index.py
SCRIPT_DIR = Path(__file__).resolve().parent # .../chat/app/utils
PROJECT_ROOT_DIR = SCRIPT_DIR.parent.parent  # .../chat/
if str(PROJECT_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT_DIR)) # Añadir la raíz del proyecto al PYTHONPATH

# Configuración básica de logging (se puede refinar si es necesario)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("verify_index_script") # Logger específico para este script

# --- Helper Functions (si son necesarias o para mejorar la legibilidad) ---
def get_brand_from_metadata(metadata: Dict[str, Any]) -> str:
    """
    Intenta obtener el nombre de marca desde los metadatos.
    Prioriza metadata['brand'], luego intenta inferir de filename o source.
    """
    # 1. Usar el campo 'brand' normalizado si existe (el más fiable)
    if 'brand' in metadata and metadata['brand']:
        return f"{metadata['brand']} (desde metadata['brand'])"
    
    # 2. Fallback: Inferir del nombre del archivo si doc_type es 'brand'
    doc_type = metadata.get('doc_type')
    filename = metadata.get('filename')
    if doc_type == 'brand' and filename:
        # Reconstrucción simple, podría no ser perfecta si el nombre original tenía caracteres especiales
        brand_from_file = filename.replace(".txt", "").replace("_", " ").title()
        return f"{brand_from_file} (inferido de filename '{filename}')"
        
    # 3. Fallback: Si no hay 'brand' o 'filename' específico de marca, indicar desconocido
    return "Marca Desconocida/No Aplicable"


async def verify_faiss_index_and_rag():
    """
    Verifica el índice FAISS y los componentes RAG cargados.
    Muestra información detallada sobre el índice y los documentos.
    """
    logger.info("--- Iniciando Verificación del Índice FAISS y Componentes RAG ---")
    
    try:
        # Importar componentes necesarios DENTRO de la función para asegurar que sys.path esté ajustado
        from app.core.config import settings
        from app.ai.rag_retriever import load_rag_components, search_relevant_documents
        # Asumimos que LangchainDocument es el tipo correcto de los documentos retornados
        from langchain.schema import Document as LangchainDocument

        logger.info(f"Usando configuración del proyecto en: {PROJECT_ROOT_DIR}")
        if not settings:
            logger.error("Settings no se cargaron correctamente. No se puede continuar.")
            return
            
        logger.info(f"Ruta de la carpeta del índice FAISS (desde settings): {settings.faiss_folder_path}")
        logger.info(f"Nombre base del índice FAISS (desde settings): {settings.faiss_index_name}")
        logger.info(f"Modelo de Embeddings a usar (desde settings): {settings.embedding_model_name}")

        # 1. Cargar componentes RAG (esto es síncrono)
        logger.info("Cargando componentes RAG (Retriever)...")
        retriever = load_rag_components() # Esta función es síncrona
        
        if not retriever:
            logger.error("FALLO al cargar componentes RAG. El retriever es None. Revisa logs anteriores para detalles.")
            return
        
        logger.info("¡Componentes RAG (Retriever) cargados exitosamente!")
        logger.info(f"Tipo de Retriever: {type(retriever)}")
        if hasattr(retriever, 'vectorstore') and hasattr(retriever.vectorstore, 'index'):
            logger.info(f"Número total de vectores en el índice FAISS del retriever: {retriever.vectorstore.index.ntotal}")
        else:
            logger.warning("No se pudo acceder a la información del índice FAISS a través del retriever.")

        # 2. Pruebas de Búsqueda con Consultas Genéricas
        test_queries = {
            "información general": None, # Búsqueda global
            "servicios de consultoría": None, # Búsqueda global
            "contacto de Javier Bazán": "consultor_javier_bazan" # Búsqueda específica para marca (espera nombre normalizado)
        }
        
        for query, target_brand_normalized in test_queries.items():
            log_query_type = f"global para '{query}'"
            if target_brand_normalized:
                log_query_type = f"para marca '{target_brand_normalized}' con query '{query}'"

            logger.info(f"\n--- Probando Búsqueda RAG ({log_query_type}) ---")
            
            # Usar la función asíncrona search_relevant_documents
            retrieved_docs: List[LangchainDocument] = await search_relevant_documents(
                retriever_instance=retriever,
                user_query=query,
                target_brand=target_brand_normalized, # Pasar el nombre normalizado
                k_final=settings.rag_default_k 
            )
            
            logger.info(f"Búsqueda para '{query}' (marca: {target_brand_normalized if target_brand_normalized else 'Global'}) devolvió {len(retrieved_docs)} documentos.")
            if not retrieved_docs:
                logger.info("No se recuperaron documentos para esta consulta/marca.")
            
            for i, doc in enumerate(retrieved_docs, 1):
                logger.info(f"  --- Documento Recuperado {i} ---")
                brand_display = get_brand_from_metadata(doc.metadata)
                logger.info(f"    Marca (interpretada): {brand_display}")
                logger.info(f"    Metadata Completa:")
                for key, value in doc.metadata.items():
                    logger.info(f"      {key}: {value}")
                logger.info(f"    Contenido (primeros 200 caracteres):")
                logger.info(f"      '{doc.page_content[:200].strip().replace(chr(10), ' ')}...'") # Reemplaza saltos de línea por espacios para el preview
            logger.info("  --- Fin Documentos Recuperados para esta Consulta ---")

        # 3. Análisis Adicional del Índice (si es posible y útil)
        # Acceder directamente al docstore si está disponible para ver todos los metadatos
        if hasattr(retriever, 'vectorstore') and hasattr(retriever.vectorstore, 'docstore') and hasattr(retriever.vectorstore.docstore, '_dict'):
            logger.info("\n--- Análisis de Metadatos de Todos los Documentos en el Docstore ---")
            all_doc_metadatas: List[Dict[str, Any]] = []
            if retriever.vectorstore.docstore._dict: #_dict contiene id -> Document
                 for langchain_doc_obj in retriever.vectorstore.docstore._dict.values():
                    if hasattr(langchain_doc_obj, 'metadata'):
                        all_doc_metadatas.append(langchain_doc_obj.metadata)

            if all_doc_metadatas:
                logger.info(f"Total de documentos en el docstore del índice: {len(all_doc_metadatas)}")
                
                brands_in_index: Dict[str, int] = {}
                doc_types_in_index: Dict[str, int] = {}
                categories_in_index: Dict[str, int] = {}

                for meta in all_doc_metadatas:
                    brand_key = meta.get('brand', 'Sin Marca (metadata)') # Usa el 'brand' normalizado
                    brands_in_index[brand_key] = brands_in_index.get(brand_key, 0) + 1
                    
                    doc_type_key = meta.get('doc_type', 'Desconocido')
                    doc_types_in_index[doc_type_key] = doc_types_in_index.get(doc_type_key, 0) + 1

                    category_key = meta.get('category', 'Sin Categoría')
                    categories_in_index[category_key] = categories_in_index.get(category_key, 0) + 1
                
                logger.info("\n  --- Distribución por 'brand' (desde metadata) ---")
                for brand_val, count in sorted(brands_in_index.items()):
                    logger.info(f"    '{brand_val}': {count} chunks")

                logger.info("\n  --- Distribución por 'doc_type' ---")
                for dt_val, count in sorted(doc_types_in_index.items()):
                    logger.info(f"    '{dt_val}': {count} chunks")

                logger.info("\n  --- Distribución por 'category' ---")
                for cat_val, count in sorted(categories_in_index.items()):
                    logger.info(f"    '{cat_val}': {count} chunks")
                
                logger.info("\n  --- Ejemplo de Metadatos del Primer Documento en Docstore ---")
                if all_doc_metadatas:
                    logger.info(f"    {all_doc_metadatas[0]}")
            else:
                logger.warning("No se pudieron extraer metadatos del docstore para análisis completo.")
        else:
            logger.warning("No se pudo acceder al docstore del vectorstore para un análisis completo de metadatos.")
            logger.info("Intenta una consulta muy genérica como 'qué es esto' para ver algunos documentos si el análisis del docstore falla.")

    except ImportError as ie_verify:
        logger.error(f"Error de importación en verify_faiss_index_and_rag: {ie_verify}. Verifica tu PYTHONPATH y estructura del proyecto.")
        logger.error(f"PYTHONPATH actual: {sys.path}")
    except Exception as e_verify:
        logger.error(f"Error durante la verificación del índice: {e_verify}", exc_info=True)
    
    logger.info("--- Fin de la Verificación del Índice FAISS y Componentes RAG ---")

if __name__ == "__main__":
    logger.info(f"Ejecutando script: {Path(__file__).name}")
    logger.info("Asegúrate de que el entorno virtual esté activado y todas las dependencias instaladas.")
    logger.info(f"Raíz del proyecto calculada: {PROJECT_ROOT_DIR}")
    logger.info("PYTHONPATH al inicio de la ejecución:")
    for pth in sys.path:
        logger.info(f"  - {pth}")
    
    # Ejecutar la función asíncrona
    asyncio.run(verify_faiss_index_and_rag())