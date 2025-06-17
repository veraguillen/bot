# app/utils/file_helpers.py
import re
from pathlib import Path
from typing import Optional
from unidecode import unidecode
from app.core.config import settings
from .logger import logger

def _normalize_brand_name(name: str) -> str:
    """
    Normaliza un nombre de marca para usarlo como nombre de archivo.
    Convierte a minúsculas, quita acentos y caracteres especiales.
    """
    if not isinstance(name, str) or not name.strip():
        return "invalid_brand_name"
        
    s = unidecode(name).lower()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'\s+', '_', s)
    s = re.sub(r'[^a-z0-9_-]', '', s)
    s = s.strip('_-')
    
    return s or "normalized_to_empty"

def get_brand_context(brand_name: str) -> Optional[str]:
    """
    Obtiene el contexto de una marca desde un archivo de texto.
    
    Args:
        brand_name: Nombre de la marca cuyo contexto se quiere obtener
        
    Returns:
        El contenido del archivo de contexto o None si no existe/hay error
    """
    # REFACTOR: Usar la nueva estructura de directorios desde settings
    brands_dir = settings.DATA_DIR_PATH / "brands"
    
    if not brands_dir.is_dir():
        logger.error(f"El directorio de marcas no existe: {brands_dir}")
        return None
        
    normalized_filename = f"{_normalize_brand_name(brand_name)}.txt"
    file_path = brands_dir / normalized_filename
    
    if not file_path.is_file():
        logger.warning(f"Archivo de contexto no encontrado para '{brand_name}' en '{file_path}'")
        return None
        
    try:
        content = file_path.read_text(encoding='utf-8').strip()
        if not content:
            logger.warning(f"Archivo de contexto para '{brand_name}' está vacío.")
            return ""
            
        logger.info(f"Contexto cargado para '{brand_name}' desde '{file_path.name}'.")
        return content
        
    except Exception as e:
        logger.error(f"Error al leer archivo de contexto para '{brand_name}': {e}", exc_info=True)
        return None
