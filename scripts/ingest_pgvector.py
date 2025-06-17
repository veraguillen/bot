#!/usr/bin/env python
# Script para vectorizar documentos de marcas en PostgreSQL con pgvector

import sys
import os
import time
import logging
import asyncio
import asyncpg
from pathlib import Path
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from datetime import datetime

# Cargar variables de entorno al inicio
load_dotenv()

# Añadir el directorio raíz del proyecto al path
script_dir = Path(__file__).parent.absolute()
root_dir = script_dir.parent
sys.path.insert(0, str(root_dir))

# Crear directorio de logs si no existe
log_dir = root_dir / "logs"
log_dir.mkdir(exist_ok=True)

# Configurar logging
logger = logging.getLogger("pgvector_brands_ingestor")
logger.setLevel(logging.DEBUG)  # Aumentado a DEBUG para más detalles

# Formato para los logs
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Handler para consola
console_handler = logging.StreamHandler()
console_handler.setFormatter(formatter)

# Handler para archivo
log_file = log_dir / "ingestion.log"
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setFormatter(formatter)

# Añadir handlers al logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)

# Importaciones de LangChain - importar después de configurar path
try:
    from langchain.schema import Document
    from langchain_community.document_loaders import DirectoryLoader, TextLoader
    from langchain_community.embeddings.huggingface import HuggingFaceEmbeddings
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_postgres import PGVector
    from app.utils.text_processing import normalize_brand_name
    LANGCHAIN_IMPORTS_OK = True
except ImportError as e:
    logger.error(f"Error importando librerías necesarias: {e}", exc_info=True)
    LANGCHAIN_IMPORTS_OK = False


def process_brand_documents(brands_dir: Path, chunk_size: int, chunk_overlap: int, min_chunk_size: int, max_chunk_size: int) -> List[Document]:
    """
    Carga y procesa documentos de marcas desde el directorio especificado.
    
    Args:
        brands_dir: Directorio con documentos de marcas (.txt)
        chunk_size: Tamaño de cada fragmento de texto
        chunk_overlap: Superposición entre fragmentos
        min_chunk_size: Tamaño mínimo de fragmento
        max_chunk_size: Tamaño máximo de fragmento
        
    Returns:
        Lista de documentos procesados con metadatos de marca
    """
    if not brands_dir.exists():
        logger.error(f"El directorio de marcas {brands_dir} no existe")
        return []
    
    try:
        # Cargar documentos desde el directorio
        logger.info(f"Cargando documentos de marcas desde {brands_dir}")
        loader = DirectoryLoader(
            str(brands_dir),
            glob="**/*.txt",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"}
        )
        documents = loader.load()
        logger.info(f"Cargados {len(documents)} documentos de marcas")
        
        if not documents:
            logger.warning(f"No se encontraron documentos .txt en {brands_dir}")
            return []
        
        # Añadir metadatos de marca a los documentos
        for doc in documents:
            file_path = doc.metadata.get("source", "")
            if not file_path:
                continue
                
            # Extraer nombre del archivo como nombre de marca
            file_name = Path(file_path).stem  # Nombre sin extensión
            
            # Normalizar el nombre de la marca
            normalized_brand = normalize_brand_name(file_name)
            
            # Añadir metadatos
            doc.metadata["brand"] = normalized_brand
            doc.metadata["file_name"] = file_name
            doc.metadata["processed_at"] = datetime.now().isoformat()
            
        # Dividir documentos en fragmentos más pequeños
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            min_chunk_size=min_chunk_size,
            max_chunk_size=max_chunk_size
        )
        split_documents = splitter.split_documents(documents)
        logger.info(f"Documentos divididos en {len(split_documents)} fragmentos")
        
        return split_documents
    
    except Exception as e:
        logger.error(f"Error procesando documentos de marcas: {e}", exc_info=True)
        return []


def delete_documents_by_source(connection_string: str, collection_name: str, source_file: str) -> bool:
    """
    Borra documentos específicos de la base de datos basándose en el archivo fuente.
    
    Args:
        connection_string: String de conexión a PostgreSQL
        collection_name: Nombre de la colección en PGVector  
        source_file: Nombre del archivo fuente a borrar
        
    Returns:
        True si el borrado fue exitoso, False en caso contrario
    """
    try:
        async def _delete_by_source():
            conn = await asyncpg.connect(connection_string)
            try:
                # Borrar documentos que coincidan con el archivo fuente
                deleted_count = await conn.execute(
                    "DELETE FROM langchain_pg_embedding WHERE cmetadata->>'source' = $1",
                    source_file
                )
                
                # También borrar de la tabla documents si existe
                try:
                    deleted_docs = await conn.execute(
                        "DELETE FROM documents WHERE source = $1",
                        source_file
                    )
                    logger.info(f"Borrados {deleted_docs.split()[-1]} documentos de la tabla 'documents' para fuente: {source_file}")
                except Exception as e:
                    logger.debug(f"No se pudo borrar de tabla 'documents' (posiblemente no existe): {e}")
                
                logger.info(f"Borrados documentos vectoriales para fuente: {source_file}")
                return True
                
            finally:
                await conn.close()
        
        # Ejecutar operación asíncrona
        asyncio.run(_delete_by_source())
        return True
        
    except Exception as e:
        logger.error(f"Error borrando documentos por fuente '{source_file}': {e}", exc_info=True)
        return False


def process_single_brand_file(file_path: Path, chunk_size: int, chunk_overlap: int, 
                             min_chunk_size: int, max_chunk_size: int) -> List[Document]:
    """
    Procesa un archivo individual de marca y retorna sus documentos.
    
    Args:
        file_path: Ruta al archivo .txt de la marca
        chunk_size: Tamaño de cada fragmento de texto
        chunk_overlap: Superposición entre fragmentos
        min_chunk_size: Tamaño mínimo de fragmento
        max_chunk_size: Tamaño máximo de fragmento
        
    Returns:
        Lista de documentos procesados con metadatos
    """
    try:
        if not file_path.exists() or not file_path.is_file():
            logger.warning(f"Archivo no encontrado: {file_path}")
            return []
        
        # Leer contenido del archivo
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        if not content:
            logger.warning(f"Archivo vacío: {file_path}")
            return []
        
        # Extraer nombre de marca del archivo
        brand_name = file_path.stem
        logger.info(f"Procesando archivo: {file_path.name} (marca: {brand_name})")
        
        # Crear documento inicial
        document = Document(
            page_content=content,
            metadata={
                "source": file_path.name,
                "brand": brand_name,
                "file_type": "txt",
                "processed_at": datetime.now().isoformat()
            }
        )
        
        # Dividir en fragmentos usando RecursiveCharacterTextSplitter
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            length_function=len,
            is_separator_regex=False,
            add_start_index=True,
            strip_whitespace=True,
            separators=["\n\n", "\n", ".", "!", "?", ";", ":", " ", ""]
        )
        
        # Configurar límites de tamaño si están disponibles
        if hasattr(splitter, '_min_chunk_size'):
            splitter._min_chunk_size = min_chunk_size
        if hasattr(splitter, '_max_chunk_size'):  
            splitter._max_chunk_size = max_chunk_size
        
        split_documents = splitter.split_documents([document])
        
        # Filtrar fragmentos por tamaño si el splitter no lo hace automáticamente
        filtered_docs = []
        for doc in split_documents:
            doc_length = len(doc.page_content.strip())
            if min_chunk_size <= doc_length <= max_chunk_size:
                # Enriquecer metadatos
                doc.metadata.update({
                    "chunk_size": doc_length,
                    "chunk_index": len(filtered_docs)
                })
                filtered_docs.append(doc)
            else:
                logger.debug(f"Fragmento filtrado por tamaño ({doc_length} caracteres): {doc.page_content[:50]}...")
        
        logger.info(f"Archivo {file_path.name} procesado: {len(split_documents)} → {len(filtered_docs)} fragmentos válidos")
        return filtered_docs
        
    except Exception as e:
        logger.error(f"Error procesando archivo {file_path}: {e}", exc_info=True)
        return []


def ingest_to_pgvector(documents: List[Document], connection_string: str, 
                      collection_name: str, recreate: bool = False) -> bool:
    """
    Ingesta documentos de marcas en PostgreSQL con pgvector.
    
    Args:
        documents: Lista de documentos a ingestar
        connection_string: String de conexión a PostgreSQL
        collection_name: Nombre de la colección en PGVector
        recreate: Si es True, elimina y recrea la colección
        
    Returns:
        True si la ingesta fue exitosa, False en caso contrario
    """
    if not documents:
        logger.warning("No hay documentos para ingestar")
        return False
    
    try:
        # Inicializar modelo de embeddings usando variable de entorno
        embedding_model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
        logger.info(f"Inicializando modelo de embeddings: {embedding_model_name}")
        embedding_function = HuggingFaceEmbeddings(
            model_name=embedding_model_name,
            cache_folder=os.path.join(os.getcwd(), "models_cache"),
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True}
        )
        
        # Configurar PGVector
        logger.info(f"Conectando a PostgreSQL, colección: {collection_name}")
        # PGVector.from_documents ya realiza la ingesta de los documentos proporcionados
        # No es necesario llamar a add_documents después
        vectorstore = PGVector.from_documents(
            documents=documents,
            embedding=embedding_function,
            collection_name=collection_name,
            connection=connection_string,
            pre_delete_collection=recreate
        )
        
        logger.info(f"Ingesta de {len(documents)} documentos completada a través de from_documents")
        logger.info("¡Ingesta completada exitosamente!")
        
        return True
    except Exception as e:
        logger.error(f"Error durante la ingesta a pgvector: {e}", exc_info=True)
        return False


def main():
    """
    Función principal del script con procesamiento archivo por archivo.
    Implementa estrategia "Borrar y Recrear" para evitar duplicados.
    """
    if not LANGCHAIN_IMPORTS_OK:
        sys.exit("Error: No se pudieron importar las librerías necesarias")
    
    # Configurar parámetros desde variables de entorno
    brands_dir_env = os.getenv("BRANDS_DIR", "./data/brands")
    brands_dir = Path(brands_dir_env)
    
    collection_name = os.getenv("VECTOR_COLLECTION_NAME", "chatbot_docs_v1")
    
    # Usar configuraciones optimizadas de chunking desde settings
    chunk_size = int(os.getenv("CHUNK_SIZE", "1200"))  # Optimizado para balance contexto/precisión
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))  # Mejorado para continuidad
    
    # Configuraciones adicionales para mejor procesamiento
    min_chunk_size = int(os.getenv("MIN_CHUNK_SIZE", "100"))  # Filtrar fragmentos muy pequeños
    max_chunk_size = int(os.getenv("MAX_CHUNK_SIZE", "1800"))  # Límite superior
    
    # Opciones de procesamiento
    recreate_entire_collection = os.getenv("RECREATE_COLLECTION", "false").lower() == "true"
    process_individual_files = not recreate_entire_collection  # Por defecto, procesar archivo por archivo
    
    # Obtener string de conexión a PostgreSQL
    db_url = os.getenv("AZURE_POSTGRES_URL")
    if not db_url:
        sys.exit("Error: No se encontró string de conexión a PostgreSQL (AZURE_POSTGRES_URL) en .env")
    
    logger.info(f"=== Iniciando ingesta a PGVector ===")
    logger.info(f"Colección: {collection_name}")
    logger.info(f"Directorio de marcas: {brands_dir}")
    logger.info(f"Tamaño de fragmento: {chunk_size}, Solapamiento: {chunk_overlap}")
    logger.info(f"Tamaño mínimo de fragmento: {min_chunk_size}, Tamaño máximo de fragmento: {max_chunk_size}")
    logger.info(f"Modo de procesamiento: {'Recrear colección completa' if recreate_entire_collection else 'Archivo por archivo (Borrar y Recrear)'}")
    
    # Verificar que el directorio de marcas existe
    if not brands_dir.exists():
        sys.exit(f"Error: El directorio de marcas {brands_dir} no existe")
    
    # Obtener lista de archivos .txt
    txt_files = list(brands_dir.glob("*.txt"))
    if not txt_files:
        logger.warning("No se encontraron archivos .txt para procesar. Finalizando.")
        sys.exit(1)
    
    logger.info(f"Archivos encontrados: {len(txt_files)}")
    
    start_time = time.time()
    
    if recreate_entire_collection:
        # Modo tradicional: procesar todos los archivos de una vez
        logger.info("=== Modo: Recreación completa de colección ===")
        documents = process_brand_documents(brands_dir, chunk_size, chunk_overlap, min_chunk_size, max_chunk_size)
        
        if not documents:
            logger.warning("No se encontraron documentos para procesar. Finalizando.")
            sys.exit(1)
            
        # Ingestar documentos a PGVector
        logger.info(f"Iniciando ingesta de {len(documents)} documentos a PGVector...")
        success = ingest_to_pgvector(documents, db_url, collection_name, True)
        
    else:
        # Modo archivo por archivo: Borrar y Recrear individual
        logger.info("=== Modo: Procesamiento archivo por archivo (Borrar y Recrear) ===")
        successful_files = 0
        failed_files = 0
        total_processed_documents = 0
        
        for txt_file in txt_files:
            logger.info(f"\n--- Procesando archivo: {txt_file.name} ---")
            
            try:
                # Paso 1: Borrar documentos existentes de este archivo
                logger.info(f"1. Borrando documentos existentes de: {txt_file.name}")
                delete_success = delete_documents_by_source(db_url, collection_name, txt_file.name)
                
                if not delete_success:
                    logger.warning(f"No se pudieron borrar documentos existentes de {txt_file.name}, continuando...")
                
                # Paso 2: Procesar el archivo
                logger.info(f"2. Procesando y troceando: {txt_file.name}")
                file_documents = process_single_brand_file(
                    txt_file, chunk_size, chunk_overlap, min_chunk_size, max_chunk_size
                )
                
                if not file_documents:
                    logger.warning(f"No se generaron documentos válidos de {txt_file.name}")
                    failed_files += 1
                    continue
                
                # Paso 3: Ingestar nuevos documentos
                logger.info(f"3. Ingresando {len(file_documents)} fragmentos de: {txt_file.name}")
                ingest_success = ingest_to_pgvector(file_documents, db_url, collection_name, False)
                
                if ingest_success:
                    successful_files += 1
                    total_processed_documents += len(file_documents)
                    logger.info(f"✅ Archivo {txt_file.name} procesado exitosamente ({len(file_documents)} fragmentos)")
                else:
                    failed_files += 1
                    logger.error(f"❌ Error procesando archivo: {txt_file.name}")
                    
            except Exception as e:
                failed_files += 1
                logger.error(f"❌ Error procesando archivo {txt_file.name}: {e}", exc_info=True)
        
        # Resumen del procesamiento archivo por archivo
        logger.info(f"\n=== Resumen del procesamiento ===")
        logger.info(f"Archivos procesados exitosamente: {successful_files}")
        logger.info(f"Archivos con errores: {failed_files}")
        logger.info(f"Total de fragmentos procesados: {total_processed_documents}")
        
        success = successful_files > 0
    
    # Mostrar resultado final
    end_time = time.time()
    elapsed_time = end_time - start_time
    
    if success:
        logger.info(f"🎉 ¡Ingesta completada exitosamente en {elapsed_time:.2f} segundos!")
    else:
        logger.error(f"❌ La ingesta falló después de {elapsed_time:.2f} segundos")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Proceso interrumpido por el usuario")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        sys.exit(1)
