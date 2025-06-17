import logging
from pathlib import Path
import sys
import hashlib
from dotenv import load_dotenv

# --- Configuración de Rutas y Logging ---
# Esto permite ejecutar el script desde la raíz del proyecto
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ingestion_script")

# --- Importaciones de Langchain y App ---
try:
    from langchain_postgres import PGVector
    from langchain_community.document_loaders import DirectoryLoader
    from langchain_huggingface import HuggingFaceEmbeddings
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain.schema import Document
    # Importamos la función que ya tenías para normalizar nombres de marcas
    from app.main.webhook_handler import normalize_brand_name
except ImportError as e:
    logger.error(f"Error importando librerías. Asegúrate de tener todo instalado. Error: {e}")
    sys.exit(1)

def ingest_data():
    """
    Lee archivos .txt de directorios específicos, los vectoriza y los guarda en PostgreSQL.
    """
    # --- Cargar configuración desde .env ---
    load_dotenv()
    db_url = os.getenv("DATABASE_URL")
    model_name = os.getenv("EMBEDDING_MODEL_NAME")
    collection_name = os.getenv("VECTOR_COLLECTION_NAME")
    kb_dir_path = os.getenv("KNOWLEDGE_BASE_DIR")
    brands_dir_path = os.getenv("BRANDS_DIR")

    if not all([db_url, model_name, collection_name]):
        logger.error("Faltan variables de entorno críticas (DATABASE_URL, EMBEDDING_MODEL_NAME, VECTOR_COLLECTION_NAME).")
        return

    logger.info("="*30 + " Iniciando Ingestión de Datos a PostgreSQL " + "="*30)

    all_documents = []
    
    # --- 1. Procesar directorio de Marcas (BRANDS_DIR) ---
    if brands_dir_path and Path(brands_dir_path).is_dir():
        logger.info(f"Procesando directorio de marcas: {brands_dir_path}")
        brands_loader = DirectoryLoader(brands_dir_path, glob="**/*.txt", show_progress=True)
        brand_docs = brands_loader.load()
        for doc in brand_docs:
            # Extraer el nombre de la marca del nombre del archivo
            file_path = Path(doc.metadata.get("source"))
            brand_name_from_file = file_path.stem # .stem obtiene el nombre sin extensión
            normalized_brand = normalize_brand_name(brand_name_from_file)
            # Añadir metadatos útiles para el filtrado posterior
            doc.metadata["doc_type"] = "brand"
            doc.metadata["brand"] = normalized_brand
            doc.metadata["filename"] = file_path.name
        all_documents.extend(brand_docs)
        logger.info(f"Cargados {len(brand_docs)} documentos de marcas.")
    else:
        logger.warning(f"El directorio BRANDS_DIR ('{brands_dir_path}') no fue encontrado. Se omitirá.")
        
    # --- 2. Procesar directorio de Conocimiento General (KNOWLEDGE_BASE_DIR) ---
    if kb_dir_path and Path(kb_dir_path).is_dir():
        logger.info(f"Procesando directorio de conocimiento general: {kb_dir_path}")
        kb_loader = DirectoryLoader(kb_dir_path, glob="**/*.txt", show_progress=True)
        kb_docs = kb_loader.load()
        for doc in kb_docs:
            doc.metadata["doc_type"] = "kb" # Conocimiento General
        all_documents.extend(kb_docs)
        logger.info(f"Cargados {len(kb_docs)} documentos de conocimiento general.")
    else:
        logger.warning(f"El directorio KNOWLEDGE_BASE_DIR ('{kb_dir_path}') no fue encontrado. Se omitirá.")
        
    if not all_documents:
        logger.error("No se encontraron documentos en ninguna de las rutas especificadas. Abortando.")
        return

    # --- 3. Dividir documentos en chunks ---
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
    chunked_documents = text_splitter.split_documents(all_documents)
    logger.info(f"Total de documentos divididos en {len(chunked_documents)} chunks.")

    # --- 4. Inicializar Embeddings y Conectar a PGVector ---
    logger.info(f"Inicializando modelo de embeddings: {model_name}")
    embedding_model = HuggingFaceEmbeddings(model_name=model_name, model_kwargs={'device': 'cpu'})
    
    logger.info("Conectando a la base de datos PostgreSQL...")
    vector_store = PGVector(
        collection_name=collection_name,
        connection=db_url,
        embedding_function=embedding_model,
    )

    # --- 5. Ingestar en la Base de Datos ---
    logger.info(f"Ingestando {len(chunked_documents)} chunks en la colección '{collection_name}'...")
    # Generar IDs para evitar duplicados si se re-ejecuta
    doc_ids = [hashlib.md5(doc.page_content.encode()).hexdigest() for doc in chunked_documents]
    vector_store.add_documents(documents=chunked_documents, ids=doc_ids)

    logger.info("="*30 + " Proceso de Ingestión Finalizado Exitosamente " + "="*30)

if __name__ == "__main__":
    ingest_data()