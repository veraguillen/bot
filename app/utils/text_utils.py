"""
Utilidades para procesamiento de texto y normalización.
"""

import re
import unicodedata
from typing import List, Optional

from langchain_core.documents import Document


def normalize_brand_for_rag(brand_name_display: str) -> str:
    """
    Normaliza un nombre de marca para uso en el sistema RAG.
    
    Esta función toma un nombre de marca original (por ejemplo, "CONSULTOR: Javier Bazán")
    y lo convierte a un formato estandarizado para usar como clave en el índice FAISS
    (por ejemplo, "consultor_javier_bazan").
    
    Args:
        brand_name_display: Nombre original de la marca
        
    Returns:
        Nombre de marca normalizado para usar como clave en el índice FAISS
    """
    if not brand_name_display or not isinstance(brand_name_display, str):
        return ""
    
    # Caso especial para "Corporativo Ehécatl" y sus variantes
    if isinstance(brand_name_display, str) and 'Eh' in brand_name_display and 'catl' in brand_name_display.lower():
        return "corporativo_ehecatl_sa_de_cv"
    
    # Convertir a minúsculas
    normalized = brand_name_display.lower()
    
    # Manejar caracteres problemáticos específicos primero
    # Carácter U+201A (single low-9 quotation mark) que aparece en "Eh‚catl"
    normalized = normalized.replace('\u201a', '').replace('‚', '')
    
    # Eliminar acentos y caracteres especiales
    normalized = unicodedata.normalize('NFKD', normalized)
    normalized = ''.join([c for c in normalized if not unicodedata.combining(c)])
    
    # Reemplazar caracteres no alfanuméricos con espacios
    # Asegurarse de que no queden caracteres especiales
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    
    # Reemplazar múltiples espacios con uno solo y eliminar espacios al inicio y final
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Reemplazar espacios con guiones bajos
    normalized = normalized.replace(' ', '_')
    
    # Eliminar prefijos comunes como "CONSULTOR: " o "MARCA: "
    prefixes_to_remove = ["consultor_", "marca_", "brand_", "empresa_"]
    for prefix in prefixes_to_remove:
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    
    # Caso especial para "Corporativo Ehécatl" - asegurar consistencia
    if "ehecatl" in normalized or "ehcatl" in normalized:
        return "corporativo_ehecatl_sa_de_cv"
    
    return normalized


def format_context_from_docs(docs: List[Document], max_length: Optional[int] = None) -> str:
    """
    Formatea una lista de documentos en un solo texto para usar como contexto en el LLM.
    
    Args:
        docs: Lista de documentos de LangChain
        max_length: Longitud máxima del contexto resultante (opcional)
        
    Returns:
        Texto formateado con el contenido de los documentos
    """
    if not docs:
        return ""
    
    # Concatenar el contenido de los documentos
    context_parts = []
    
    for i, doc in enumerate(docs):
        if not hasattr(doc, 'page_content') or not doc.page_content:
            continue
            
        # Obtener metadatos relevantes
        metadata = getattr(doc, 'metadata', {})
        source = metadata.get('source', f"Documento {i+1}")
        brand = metadata.get('brand', '')
        
        # Formatear el fragmento con metadatos
        fragment = f"--- Fragmento de '{source}'"
        if brand:
            fragment += f" (Marca: {brand})"
        fragment += " ---\n"
        fragment += doc.page_content.strip()
        fragment += "\n\n"
        
        context_parts.append(fragment)
    
    # Unir todos los fragmentos
    full_context = "".join(context_parts)
    
    # Truncar si es necesario
    if max_length and len(full_context) > max_length:
        full_context = full_context[:max_length] + "..."
    
    return full_context


def clean_and_validate_query(query: str) -> str:
    """
    Limpia y valida una consulta de usuario para búsqueda RAG.
    
    Args:
        query: Consulta original del usuario
        
    Returns:
        Consulta limpia y validada
    """
    if not query or not isinstance(query, str):
        return ""
    
    # Eliminar caracteres especiales y espacios extras
    cleaned_query = re.sub(r'[^\w\s.,;:¿?¡!]', ' ', query)
    cleaned_query = re.sub(r'\s+', ' ', cleaned_query).strip()
    
    # Truncar consultas muy largas
    max_query_length = 500
    if len(cleaned_query) > max_query_length:
        cleaned_query = cleaned_query[:max_query_length]
    
    return cleaned_query
