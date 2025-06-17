"""
Utilidades para el procesamiento de texto compartidas entre diferentes componentes.
Este módulo contiene funciones de procesamiento de texto que se utilizan en múltiples partes
de la aplicación, para evitar acoplamientos circulares y promover la reutilización.
"""

import re
from unidecode import unidecode
from typing import Dict

from app.utils.logger import logger
from app.ai.rag_prompt_builder import BRAND_PROFILES, BRAND_NAME_MAPPING, normalize_brand_name_for_search

def normalize_brand_name(name: str) -> str:
    """Normaliza el nombre de una marca/consultor para uso en recuperación RAG.
    
    Args:
        name: Nombre de la marca o consultor (ej., 'CONSULTOR: Javier Bazán')
        
    Returns:
        Nombre exacto como aparece en BRAND_PROFILES o versión normalizada
    """
    if not isinstance(name, str) or not name.strip():
        return "invalid_brand_name"
    
    # PRIMERO: Revisar casos especiales directamente (sin normalizar)
    brand_name_lower = name.lower().strip()
    
    # CASO ESPECIAL: Detectar específicamente "Javier Bazán"
    if "javier" in brand_name_lower and any(x in brand_name_lower for x in ["baz", "bazan", "bazán"]):
        exact_name = "CONSULTOR: Javier Bazán"
        logger.info(f"CASO ESPECIAL JAVIER EN WEBHOOK: '{name}' → '{exact_name}'")
        return exact_name
    
    # CASO ESPECIAL: Detectar específicamente "Corporativo Ehécatl"
    # Primero tratar el carácter especial U+201A en "Eh‚catl"
    if '‚' in brand_name_lower or '‚' in name:
        # Si contiene este carácter especial, es casi seguro que es Corporativo Ehécatl
        exact_name = "Corporativo Ehécatl SA de CV"
        logger.info(f"CASO ESPECIAL CARACTER U+201A DETECTADO EN: '{name}' → '{exact_name}'")
        return exact_name
    
    if "corporativo" in brand_name_lower and any(x in brand_name_lower for x in ["eh", "ehe", "ehecatl", "ehcatl", "catl"]):
        exact_name = "Corporativo Ehécatl SA de CV"
        logger.info(f"CASO ESPECIAL CORPORATIVO EN WEBHOOK: '{name}' → '{exact_name}'")
        return exact_name
        
    # CASO ESPECIAL: Detectar específicamente "Universidad para el Desarrollo Digital"
    if ("universidad" in brand_name_lower and "desarrollo" in brand_name_lower and "digital" in brand_name_lower) or \
       ("udd" in brand_name_lower) or \
       ("universidad_desarrollo_digital" in brand_name_lower):
        exact_name = "Universidad para el Desarrollo Digital (UDD)"
        logger.info(f"CASO ESPECIAL UDD EN WEBHOOK: '{name}' → '{exact_name}'")
        return exact_name
    
    # 1. Verificar si el nombre exacto existe en BRAND_PROFILES
    if name in BRAND_PROFILES:
        return name
    
    try:
        # 2. Normalizar el nombre para la búsqueda
        normalized_brand = normalize_brand_name_for_search(name)
        logger.info(f"Nombre normalizado en webhook_handler: '{normalized_brand}'")
        
        # 3. Buscar en el mapeo de nombres normalizados
        if normalized_brand in BRAND_NAME_MAPPING:
            exact_name = BRAND_NAME_MAPPING[normalized_brand]
            logger.info(f"MARCA NORMALIZADA: '{name}' → '{exact_name}' (usando mapeo directo)")
            return exact_name
        
        # 4. Intentar coincidencia parcial
        for norm_key, exact_key in BRAND_NAME_MAPPING.items():
            if norm_key in normalized_brand or normalized_brand in norm_key:
                logger.info(f"MARCA NORMALIZADA: '{name}' → '{exact_key}' (usando coincidencia parcial)")
                return exact_key
    except Exception as e:
        logger.error(f"Error al normalizar nombre de marca en webhook: {e}")
    
    # 5. Si todo falla, aplicar normalización estándar como fallback
    # Dar tratamiento especial a caracteres problemáticos
    s = name.replace('ñ', 'n').replace('Ñ', 'N')
    s = name.replace('‹', '').replace('›', '')
    s = name.replace('', 'e').replace('', 'e')
    
    # Luego aplicar unidecode para otros caracteres especiales
    try:
        s = unidecode(s).lower()
    except Exception:
        s = ''.join(c.lower() for c in name if c.isalnum() or c.isspace())
    
    # Eliminar prefijos comunes
    s = re.sub(r'^(empresa:|consultor:|marca:|cliente:)\s*', '', s, flags=re.IGNORECASE)
    
    # Reemplazar caracteres no alfanuméricos con espacios
    s = re.sub(r'[^\w\s-]', ' ', s)
    
    # Reemplazar múltiples espacios con uno solo y convertir a guión bajo
    s = re.sub(r'\s+', '_', s.strip())
    
    logger.warning(f"MARCA NO RECONOCIDA EN WEBHOOK: '{name}' normalizada como '{s}' (sin coincidencia en el mapeo)")
    
    # Eliminar caracteres no deseados (excepto _ y -)
    s = re.sub(r'[^a-z0-9_-]', '', s)
    
    # Eliminar guiones bajos del principio y final
    s = s.strip('_')
    
    return s if s else "empty_brand_name"

def detect_scheduling_intent(user_input: str) -> bool:
    """
    Detecta si el usuario tiene la intención de agendar una cita.
    
    Args:
        user_input: Texto ingresado por el usuario.
        
    Returns:
        True si se detecta intención de agendamiento, False en caso contrario.
    """
    user_input_lower = user_input.lower()
    scheduling_keywords = ['agend', 'cita', 'reunion', 'reunión', 'calendario', 
                         'visita', 'agendar', 'programar', 'reservar', 'consulta',
                         'entrevista', 'hora', 'horario', 'disponible', 'disponibilidad']
    
    return any(keyword in user_input_lower for keyword in scheduling_keywords)
