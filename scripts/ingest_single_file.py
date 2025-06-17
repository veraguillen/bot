#!/usr/bin/env python
"""
Script para ingestar un archivo específico con estrategia Borrar y Recrear.
Útil para actualizar archivos individuales sin afectar toda la colección.

Uso:
    python scripts/ingest_single_file.py consultor_javier_bazan.txt
    python scripts/ingest_single_file.py --all  # Procesar todos los archivos
"""

import sys
import os
import argparse
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Añadir el directorio raíz del proyecto al path
script_dir = Path(__file__).parent.absolute()
root_dir = script_dir.parent
sys.path.insert(0, str(root_dir))

# Importar funciones del script principal
from scripts.ingest_pgvector import (
    delete_documents_by_source,
    process_single_brand_file,
    ingest_to_pgvector
)

# Configurar logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/ingest_single_file.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


def ingest_single_file(filename: str) -> bool:
    """
    Ingesta un archivo específico usando estrategia Borrar y Recrear.
    
    Args:
        filename: Nombre del archivo .txt a procesar
        
    Returns:
        True si fue exitoso, False en caso contrario
    """
    # Configuraciones desde variables de entorno
    brands_dir = Path(os.getenv("BRANDS_DIR", "./data/brands"))
    collection_name = os.getenv("VECTOR_COLLECTION_NAME", "chatbot_docs_v1")
    db_url = os.getenv("AZURE_POSTGRES_URL")
    
    # Parámetros de chunking
    chunk_size = int(os.getenv("CHUNK_SIZE", "1200"))
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "150"))
    min_chunk_size = int(os.getenv("MIN_CHUNK_SIZE", "100"))
    max_chunk_size = int(os.getenv("MAX_CHUNK_SIZE", "1800"))
    
    if not db_url:
        logger.error("Error: AZURE_POSTGRES_URL no encontrada en variables de entorno")
        return False
    
    # Verificar que el archivo existe
    file_path = brands_dir / filename
    if not file_path.exists():
        logger.error(f"Error: Archivo {filename} no encontrado en {brands_dir}")
        return False
    
    logger.info(f"=== Procesando archivo individual: {filename} ===")
    logger.info(f"Archivo: {file_path}")
    logger.info(f"Colección: {collection_name}")
    logger.info(f"Chunking: {chunk_size} chars, overlap {chunk_overlap}")
    
    try:
        # Paso 1: Borrar documentos existentes
        logger.info(f"1. Borrando documentos existentes de: {filename}")
        delete_success = delete_documents_by_source(db_url, collection_name, filename)
        
        if not delete_success:
            logger.warning(f"No se pudieron borrar documentos existentes, continuando...")
        
        # Paso 2: Procesar archivo
        logger.info(f"2. Procesando y troceando archivo: {filename}")
        documents = process_single_brand_file(
            file_path, chunk_size, chunk_overlap, min_chunk_size, max_chunk_size
        )
        
        if not documents:
            logger.error(f"Error: No se generaron documentos válidos de {filename}")
            return False
        
        # Paso 3: Ingestar nuevos documentos
        logger.info(f"3. Ingresando {len(documents)} fragmentos a la base de datos")
        ingest_success = ingest_to_pgvector(documents, db_url, collection_name, False)
        
        if ingest_success:
            logger.info(f"✅ Archivo {filename} procesado exitosamente ({len(documents)} fragmentos)")
            return True
        else:
            logger.error(f"❌ Error durante la ingesta de {filename}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error procesando {filename}: {e}", exc_info=True)
        return False


def main():
    """Función principal del script."""
    parser = argparse.ArgumentParser(description="Ingestar archivo específico con estrategia Borrar y Recrear")
    parser.add_argument("filename", nargs='?', help="Nombre del archivo .txt a procesar")
    parser.add_argument("--all", action="store_true", help="Procesar todos los archivos individualmente")
    parser.add_argument("--list", action="store_true", help="Listar todos los archivos disponibles")
    
    args = parser.parse_args()
    
    brands_dir = Path(os.getenv("BRANDS_DIR", "./data/brands"))
    
    if args.list:
        # Listar archivos disponibles
        txt_files = list(brands_dir.glob("*.txt"))
        if txt_files:
            print("Archivos disponibles:")
            for file in txt_files:
                print(f"  - {file.name}")
        else:
            print("No se encontraron archivos .txt")
        return
    
    if args.all:
        # Procesar todos los archivos
        txt_files = list(brands_dir.glob("*.txt"))
        if not txt_files:
            logger.error("No se encontraron archivos .txt para procesar")
            sys.exit(1)
        
        logger.info(f"Procesando {len(txt_files)} archivos individualmente...")
        successful = 0
        failed = 0
        
        for txt_file in txt_files:
            if ingest_single_file(txt_file.name):
                successful += 1
            else:
                failed += 1
        
        logger.info(f"Resumen: {successful} exitosos, {failed} fallidos")
        if failed > 0:
            sys.exit(1)
    
    elif args.filename:
        # Procesar archivo específico
        if not args.filename.endswith('.txt'):
            args.filename += '.txt'
        
        success = ingest_single_file(args.filename)
        if not success:
            sys.exit(1)
    
    else:
        # Mostrar ayuda si no se proporcionan argumentos
        parser.print_help()
        print("\nEjemplos:")
        print("  python scripts/ingest_single_file.py consultor_javier_bazan.txt")
        print("  python scripts/ingest_single_file.py --all")
        print("  python scripts/ingest_single_file.py --list")


if __name__ == "__main__":
    main()
