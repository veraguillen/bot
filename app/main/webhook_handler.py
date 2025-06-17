# app/main/webhook_handler.py
from __future__ import annotations

import re
import httpx

# Palabras para detección de contenido inapropiado
INAPPROPRIATE_WORDS = [
    "tonto", "estúpido", "idiota", "imbécil", "inútil", "basura", "mierda",
    "pendejo", "estupidez", "incompetente", "ridículo", "absurdo", "pésimo",
    "basura", "porquería", "malo", "horrible", "patetico", "odio", "detesto",
    "no sirves", "no funciona", "no entiende", "aprende", "no sabes"
]

# Conjunto de palabras clave para reiniciar la conversación
RESET_KEYWORDS = {"menu", "menú", "reiniciar", "reset", "cancelar"}

# Conjunto de palabras clave para salir/terminar la conversación
EXIT_KEYWORDS = {"salir", "adios", "adiós", "chao", "hasta luego", "terminar", "finalizar"}

# Palabras clave que pueden indicar intención de agendar
SCHEDULING_KEYWORDS = {
    "agendar", "cita", "reunión", "reunir", "hablar", "charlar", "conversar", "calendario", 
    "programar", "fecha", "hora", "disponible", "disponibilidad", "llamada", "disponibles",
    "cuando", "cuándo", "agendar cita", "quiero agendar", "calendly", "agenda", "reuniones",
    "atendiendo", "horario", "horarios", "consulta", "consultar", "llamarme", "videollamada",
    "consultoría", "consultoria", "zoom", "meet", "teams"
}

# Palabras clave que pueden indicar solicitud de información de contacto
CONTACT_INFO_KEYWORDS = {
    "contacto", "contactar", "comunicar", "comunicarme", "email", "correo", "teléfono", "telefono",
    "whatsapp", "número", "numero", "celular", "móvil", "movil", "dirección", "direccion", 
    "ubicación", "ubicacion", "sitio web", "página", "pagina", "sitio", "web", "redes sociales",
    "facebook", "instagram", "twitter", "linkedin", "contactarles", "contactarlos", "contactarte",
    "datos de contacto", "información de contacto", "contactarme", "cómo contacto", "como contacto",
    "cómo les contacto", "como les contacto", "cómo te contacto", "como te contacto",
    "donde los encuentro", "dónde los encuentro", "donde los hallo", "dónde los hallo",
    "donde puedo encontrarlos", "dónde puedo encontrarlos", "manera de contactar"
}

def _contains_contact_info_keywords(text: str) -> bool:
    """Detecta si el texto contiene palabras clave relacionadas con solicitud de información de contacto."""
    text_normalized = text.lower()
    
    # Buscar coincidencias exactas de palabras clave
    if any(keyword in text_normalized for keyword in CONTACT_INFO_KEYWORDS):
        return True
    
    # Patrones de frases comunes para solicitar contacto
    contact_phrases = [
        "como (te|los|les) (puedo )?contact",  # Cómo los contacto, cómo te puedo contactar, etc.
        "(datos|informacion|información) (de |para )?contacto",
        "(medio|forma|manera) (de |para )?contact",
        "(quiero|necesito|me gustaria|me gustaría) contacta",
        "(como|cómo) (puedo )?(comunicarme|contactar)"
    ]
    
    # Buscar patrones usando expresiones regulares
    for pattern in contact_phrases:
        if re.search(pattern, text_normalized):
            return True
            
    return False

def _contains_scheduling_keywords(text: str) -> bool:
    """Detecta si el texto contiene palabras clave relacionadas con agendamiento."""
    text_normalized = text.lower()
    return any(keyword in text_normalized for keyword in SCHEDULING_KEYWORDS)

def contains_inappropriate_content(text: str) -> bool:
    """
    Detecta si un texto contiene palabras inapropiadas o insultos.
    
    Args:
        text: El texto a analizar
        
    Returns:
        True si contiene contenido inapropiado, False en caso contrario
    """
    text_lower = text.lower()
    
    # Verificar insultos directos
    for word in INAPPROPRIATE_WORDS:
        if word in text_lower:
            return True
            
    # Verificar frases de frustración
    frustration_patterns = [
        r"\bque (?:mal|pesimo|horrible)\b",
        r"\bno (?:sirves|funciona|entiendes?)\b",
        r"\best[aá]s (?:mal|equivocad[oa]|confundid[oa])\b",
        r"\beres (?:un[ao]? )?(?:ton|idiot|estupid|inutil)"
    ]
    
    for pattern in frustration_patterns:
        if re.search(pattern, text_lower):
            return True
    
    return False

# FIX: Cambiado de importación relativa a absoluta para mayor robustez en Docker
# Import state constants from state_manager
from app.main.state_manager import (
    STAGE_SELECTING_BRAND,
    STAGE_AWAITING_ACTION,
    STAGE_AWAITING_QUERY_FOR_RAG,
    STAGE_MAIN_CHAT_RAG,
    STAGE_PROVIDING_SCHEDULING_INFO,
    STAGE_COLLECTING_NAME,
    STAGE_COLLECTING_EMAIL,
    STAGE_COLLECTING_PHONE,
    STAGE_COLLECTING_PURPOSE,
    remove_last_user_message_from_history
)
from typing import Dict, Any, Optional, List, Union, Set, TYPE_CHECKING
from datetime import date, timedelta, datetime, timezone
from unidecode import unidecode

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

# Importaciones de la aplicación
from app.core.config import settings
from app.utils.file_helpers import get_brand_context
from app.utils.text_processing import normalize_brand_name, detect_scheduling_intent
from app.ai.rag_prompt_builder import BRAND_PROFILES, BRAND_NAME_MAPPING, normalize_brand_name_for_search
from app.utils.logger import logger
import app.utils.validation_utils as local_validators
from app.ai.rag_retriever import search_relevant_documents
from app.utils.text_processing import normalize_brand_name

# Importaciones condicionales para evitar importaciones circulares
if TYPE_CHECKING:
    from app.models.webhook_models import WhatsAppMessage
    from app.models.company_models import Company

# Conjunto para rastrear usuarios en transición al flujo RAG
_pending_rag_transitions = set()

def format_context_from_docs(docs: List[Any]) -> str:
    """
    Formatea una lista de documentos en un string de contexto legible.
    
    Args:
        docs: Lista de documentos devueltos por el retriever
        
    Returns:
        String formateado con el contenido de los documentos
    """
    if not docs:
        return "No se encontró información relevante."
        
    context_parts = ["Información relevante encontrada:\n"]
    
    for i, doc in enumerate(docs, 1):
        # Extraer el contenido del documento
        content = getattr(doc, 'page_content', str(doc))
        
        # Extraer metadatos si están disponibles
        metadata = {}
        if hasattr(doc, 'metadata') and isinstance(doc.metadata, dict):
            metadata = doc.metadata
            
        # Formatear la información
        context_parts.append(f"{i}. {content[:500]}")  # Limitar longitud
        
        # Añadir metadatos relevantes si existen
        if 'source' in metadata:
            context_parts.append(f"   Fuente: {metadata['source']}")
        if 'brand' in metadata:
            context_parts.append(f"   Marca: {metadata['brand']}")
            
        context_parts.append("")
    
    return "\n".join(context_parts)

async def update_user_profile(
    db_session: AsyncSession,
    user_id: str,
    platform: str,
    profile_name: str
) -> None:
    """
    Actualiza la información del perfil del usuario en la base de datos.
    Si el usuario no existe, crea un nuevo registro.
    """
    from app.models.user_state import UserState  # Usar UserState en lugar de User
    try:
        # Buscar el usuario por ID y plataforma
        user_state = await db_session.get(UserState, (user_id, platform))
        
        if not user_state:
            # Si no existe, crear un nuevo registro
            user_state = UserState(
                user_id=user_id,
                platform=platform,
                collected_name=profile_name,
                is_subscribed=True,
                stage="selecting_brand"
            )
            db_session.add(user_state)
        elif not user_state.collected_name:
            # Si existe pero no tiene nombre, actualizarlo
            user_state.collected_name = profile_name
            
        await db_session.commit()
        logger.info(f"Perfil de usuario {user_id} actualizado exitosamente.")
        
    except Exception as e:
        logger.error(f"Error al actualizar perfil de usuario {user_id}: {e}")
        await db_session.rollback()
        # No relanzar la excepción para no interrumpir el flujo principal

from unidecode import unidecode
import re
import httpx

# Función para normalizar nombres de marcas para recuperación de documentos RAG
from app.ai.rag_prompt_builder import BRAND_NAME_MAPPING, BRAND_PROFILES, normalize_brand_name_for_search


# Conjunto para rastrear usuarios en transición al flujo RAG
_pending_rag_transitions = set()

# FIX: Cambiado de importación relativa a absoluta
from app.models.webhook_models import (
    WhatsAppPayload, WhatsAppMessage, WhatsAppInteractive,
    WhatsAppButtonReply, WhatsAppInteractiveListReply, WhatsAppContact
)
# Asegúrate que UserState esté bien definido y se importe.
# from app.models.user_state import UserState # Si lo tienes en un modelo separado de DB
# O si es una clase Pydantic o dataclass para el estado en memoria/sesión:
from pydantic import BaseModel # Ejemplo, ajusta a tu implementación

class UserStateModel(BaseModel): # Ejemplo de modelo Pydantic para el estado
    user_id: str
    platform: str
    stage: str
    current_brand_id: Optional[int] = None
    collected_name: Optional[str] = None
    collected_email: Optional[str] = None
    purpose_of_inquiry: Optional[str] = None
    # ... otros campos de estado que necesites

# FIX: Cambiado de importación relativa a absoluta
from app.models.company_models import Company

async def _handle_contact_info_request(db_session: AsyncSession, current_brand_id: int) -> str:
    """Genera una respuesta con la información de contacto específica de la marca.
    
    Args:
        db_session: Sesión de base de datos
        current_brand_id: ID de la marca actual
        
    Returns:
        Mensaje con la información de contacto formateada
    """
    try:
        company_obj = await get_company_by_id(db_session, current_brand_id)
        if not company_obj:
            return "Lo siento, no puedo proporcionar información de contacto en este momento. Por favor, intenta nuevamente más tarde."
            
        brand_name = company_obj.name
        normalized_brand_name = normalize_brand_name(brand_name)
        brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default", {}))
        
        # Obtener información de contacto del perfil de la marca
        contact_info = brand_profile.get("contact_info_notes", "")
        website = brand_profile.get("website", "")
        contact_email = brand_profile.get("contact_email", "")
        contact_phone = brand_profile.get("contact_phone", "")
        # Siempre usamos la URL de agendamiento de las variables de entorno para consistencia
        scheduling_url = settings.CALENDLY_GENERAL_SCHEDULING_LINK if hasattr(settings, "CALENDLY_GENERAL_SCHEDULING_LINK") and settings.CALENDLY_GENERAL_SCHEDULING_LINK else ""
        
        # Construir mensaje con la información de contacto
        message = f"*Información de contacto de {brand_name}*\n\n"
        
        if contact_info:
            message += f"{contact_info}\n\n"
        else:
            message += "Aquí tienes los datos disponibles para contactar:\n\n"
            
        # Siempre incluir el enlace de agendamiento
        message += f"🗓️ *Agendar una cita:* {scheduling_url}\n"
        
        # Incluir sitio web si está disponible en el perfil de la marca
        if website:
            message += f"🌐 *Sitio web:* {website}\n"
            
        # Incluir email si está disponible en el perfil de la marca
        if contact_email:
            message += f"📧 *Email:* {contact_email}\n"
            
        # Incluir teléfono si está disponible en el perfil de la marca
        if contact_phone:
            message += f"📞 *Teléfono:* {contact_phone}\n"
            
        message += "\n¿Hay algo más en lo que pueda ayudarte?"
        return message
    except Exception as e:
        logger.error(f"Error al generar información de contacto: {str(e)}", exc_info=True)
        return "Disculpa, tuvimos un problema al recuperar la información de contacto. Por favor, intenta nuevamente más tarde."
# FIX: Cambiado de importación relativa a absoluta
from app.core.config import settings
# FIX: Cambiado de importación relativa a absoluta
from app.utils.file_helpers import get_brand_context
# FIX: Cambiado de importación relativa a absoluta
from app.utils.logger import logger
# FIX: Cambiado de importación relativa a absoluta
from app.utils import validation_utils as local_validators

# FIX: Cambiado de importación relativa a absoluta
from app.main.state_manager import (
    get_or_create_user_state, # Esta función debe devolver un objeto UserStateModel o similar
    update_user_state_db,     # Esta función debe tomar el UserStateModel y persistir los cambios
    get_company_selection_message, get_action_selection_message,
    get_company_id_by_selection, get_company_by_id,
    reset_user_to_brand_selection,
    update_user_subscription_status, is_user_subscribed,
    get_conversation_history, add_to_conversation_history,
    STAGE_SELECTING_BRAND, STAGE_AWAITING_ACTION, # Renombrado desde STAGE_AWAITING_ACTION_CHOICE
    STAGE_MAIN_CHAT_RAG, STAGE_PROVIDING_SCHEDULING_INFO,
    STAGE_COLLECTING_NAME, STAGE_COLLECTING_EMAIL, STAGE_COLLECTING_PHONE, STAGE_COLLECTING_PURPOSE,
    # Considera un nuevo estado si es necesario después de mostrar info de agendamiento:
    # STAGE_POST_SCHEDULING_INFO 
)

from app.api.meta import send_whatsapp_message as _send_whatsapp_message_base

# Función envoltoria para send_whatsapp_message que pasa automáticamente el objeto request
async def send_whatsapp_message(to: str, message_payload: Union[str, Dict[str, Any]], interactive_buttons=None):
    """Wrapper para enviar mensajes de WhatsApp pasando automáticamente el request actual.
    
    Esta función obtiene el request actual del contexto de ejecución y lo pasa a la función
    base para asegurar que se use el cliente HTTP compartido.
    """
    # Obtenemos el request del contexto actual
    import inspect
    frame = inspect.currentframe()
    request = None
    
    # Buscamos request en la pila de llamadas
    while frame:
        if 'request' in frame.f_locals:
            request = frame.f_locals['request']
            break
        frame = frame.f_back
    
    # Llamamos a la función base pasando el request
    return await _send_whatsapp_message_base(to, message_payload, interactive_buttons, request=request)
from app.api.calendly import get_available_slots, get_scheduling_link
from app.api.llm_client import get_llm_response
from app.ai.rag_retriever import search_relevant_documents
from app.ai.rag_prompt_builder import build_llm_prompt, BRAND_PROFILES

RESET_KEYWORDS = {"menu", "menú", "inicio", "reset", "/reset", "/menu", "volver", "cambiar marca", "salir", "cancelar", "principal"}
# Palabras clave para dar de baja al usuario (desuscribirse completamente del servicio)
OPT_OUT_KEYWORDS = {"baja", "unsubscribe", "no quiero mensajes", "cancelar mensajes", "detener mensajes", "no más mensajes", "desuscribir", "quitar suscripción"}
OPT_IN_KEYWORDS = {"start", "alta", "subscribe", "quiero mensajes", "iniciar mensajes", "continuar mensajes"}

# --- Funciones Helper (normalize_brand_name, format_context_from_docs, format_available_slots_message se mantienen igual, omitidas por brevedad) ---
# ... normalize_brand_name ...
# ... format_context_from_docs ...
# ... format_available_slots_message ...

async def _handle_providing_scheduling_info(
    db_session: AsyncSession, 
    current_user_state_obj: UserStateModel, # Ajustado al modelo de estado
    current_brand_id: Optional[int]
) -> Optional[Union[str, Dict[str, Any]]]:
    sender_user_id_for_log = f"{current_user_state_obj.platform}:{current_user_state_obj.user_id}"
    
    logger.info(f"_handle_providing_scheduling_info: Iniciando para usuario {sender_user_id_for_log}, BrandID: {current_brand_id}")

    if not settings.CALENDLY_EVENT_TYPE_URI or not settings.CALENDLY_API_KEY:
        logger.error(f"_handle_providing_scheduling_info: CRÍTICO - CALENDLY_EVENT_TYPE_URI o CALENDLY_API_KEY no están configurados. Usuario: {sender_user_id_for_log}")
        # No cambiar el estado aquí, dejar que el llamador decida el fallback
        return "Lo siento, hay un problema con la configuración de nuestro sistema de agendamiento. Por favor, intenta más tarde o escribe 'menu' para volver a las opciones principales."

    company = await get_company_by_id(db_session, current_brand_id) if current_brand_id else None
    company_name_display = company.name if company else "nuestro equipo"
    user_first_name = current_user_state_obj.collected_name.split()[0] if current_user_state_obj.collected_name else "tú"
    logger.debug(f"_handle_providing_scheduling_info: Compañía: '{company_name_display}', Nombre usuario: '{user_first_name}'")

    response_parts = [f"¡Genial, {user_first_name}! Me alegra poder ayudarte."]
    purpose = current_user_state_obj.purpose_of_inquiry
    if not purpose or purpose.startswith("🗓️") or purpose.startswith("❓"): # Si el propósito es el título del botón, usar algo genérico
        purpose = "tu consulta"
    response_parts.append(f"Para coordinar tu cita sobre '{purpose}' con *{company_name_display}*, te comparto lo siguiente:")
    
    slots_message_part = "No pude obtener los horarios disponibles en este momento."
    try:
        slots_days_to_check = settings.CALENDLY_DAYS_TO_CHECK if settings.CALENDLY_DAYS_TO_CHECK and settings.CALENDLY_DAYS_TO_CHECK > 0 else 7
        logger.debug(f"_handle_providing_scheduling_info: Buscando slots en Calendly para los próximos {slots_days_to_check} días.")
        start_date = date.today()
        end_date = start_date + timedelta(days=slots_days_to_check)
        available_slots_data = await get_available_slots(str(settings.CALENDLY_EVENT_TYPE_URI), start_date, end_date)
        
        if available_slots_data:
            logger.debug(f"_handle_providing_scheduling_info: Slots obtenidos de Calendly: {len(available_slots_data)} slots. Formateando...")
            slots_message_part = format_available_slots_message(available_slots_data)
        else:
            logger.info(f"_handle_providing_scheduling_info: No se encontraron slots disponibles en Calendly para {sender_user_id_for_log} en el rango especificado.")
            slots_message_part = "Lo siento, no encontré horarios disponibles en los próximos días para este evento."
    except Exception as e:
        logger.error(f"_handle_providing_scheduling_info: Error al obtener/formatear slots de Calendly para {sender_user_id_for_log}: {e}", exc_info=True)
    response_parts.append(slots_message_part)

    link_message_part = "No pude generar un enlace de agendamiento en este momento."
    try:
        # Usar directamente CALENDLY_GENERAL_SCHEDULING_LINK para garantizar consistencia
        if hasattr(settings, "CALENDLY_GENERAL_SCHEDULING_LINK") and settings.CALENDLY_GENERAL_SCHEDULING_LINK:
            scheduling_link_url = settings.CALENDLY_GENERAL_SCHEDULING_LINK
            # Asegurarse de que el enlace sea destacado y visible
            link_message_part = f"\n📌 *Aquí tienes el enlace para elegir el horario que mejor te convenga:*\n\n{scheduling_link_url}\n"
            logger.info(f"_handle_providing_scheduling_info: Usando enlace general de agendamiento: {scheduling_link_url}")
        else:
            logger.warning(f"_handle_providing_scheduling_info: No se pudo proporcionar enlace de agendamiento para {sender_user_id_for_log} porque CALENDLY_GENERAL_SCHEDULING_LINK no está configurado.")
            link_message_part = "\n❌ No pude generar un enlace de agendamiento. Por favor, escribe 'menu' e intenta nuevamente."
    except Exception as e:
        logger.error(f"_handle_providing_scheduling_info: Error al generar enlace de Calendly para {sender_user_id_for_log}: {e}", exc_info=True)
    response_parts.append(link_message_part)

    response_parts.append("\nRecibirás una confirmación por correo después de agendar. Si necesitas ayuda con algo más, no dudes en preguntar o escribe 'menu' para ver otras opciones.")
    
    final_response_message = "\n\n".join(filter(None, response_parts))
    
    # IMPORTANTE: No resetear el estado aquí a STAGE_AWAITING_ACTION.
    # El llamador (handle_whatsapp_message) decidirá el siguiente estado.
    # Por ejemplo, podría transicionar a STAGE_MAIN_CHAT_RAG para permitir preguntas de seguimiento.
    logger.info(f"_handle_providing_scheduling_info: Respuesta de agendamiento preparada para {sender_user_id_for_log}.")
    return final_response_message

async def handle_whatsapp_message(
    message_obj_from_payload: WhatsAppMessage,
    user_profile_name_from_webhook: Optional[str],
    platform_name: str,
    db_session: AsyncSession,
    request: Request  # request puede no ser necesario aquí, pero se mantiene si lo usas en otro lado
) -> Dict[str, Any]:
    from_phone = message_obj_from_payload.from_number
    user_key = f"{platform_name}:{from_phone}"
    
    user_input_text = ""
    button_id_pressed = None
    
    if message_obj_from_payload.text and hasattr(message_obj_from_payload.text, 'body'):
        user_input_text = message_obj_from_payload.text.body.strip()
    
    if message_obj_from_payload.interactive:
        interactive = message_obj_from_payload.interactive
        if interactive.type == "button_reply" and interactive.button_reply:
            button_id_pressed = interactive.button_reply.id
            # Usar el title del botón como user_input_text si no hay texto (o para consistencia)
            user_input_text = interactive.button_reply.title.strip() 
            logger.info(f"Botón presionado ID: '{button_id_pressed}', Título: '{user_input_text}'")
        elif interactive.type == "list_reply" and interactive.list_reply:
            button_id_pressed = interactive.list_reply.id # ID de la opción de lista
            user_input_text = interactive.list_reply.title.strip()
            logger.info(f"Opción de lista seleccionada ID: '{button_id_pressed}', Título: '{user_input_text}'")

    if not user_input_text:
        logger.warning(f"Mensaje sin contenido procesable (texto o botón/lista) recibido de {user_key}")
        return {"status": "ignored", "reason": "empty_or_unhandled_message_content"}

    logger.info(f"Procesando input para {user_key}: '{user_input_text}' (Botón ID: {button_id_pressed})")

    current_user_state_obj: UserStateModel = await get_or_create_user_state(
        db_session=db_session,
        user_id=from_phone,
        platform=platform_name,
        display_name=user_profile_name_from_webhook
    )

    if not await is_user_subscribed(db_session, from_phone, platform_name):
        # (Lógica de no suscrito se mantiene)
        logger.info(f"Usuario {user_key} no está suscrito. Ignorando mensaje.")
        return {"status": "ignored", "reason": "user_not_subscribed"}
        
    # Verificar si la sesión fue finalizada explícitamente y se encuentra en selección de marca
    # Obtener el estado actual y la marca actual al inicio para usarlos en varios flujos
    current_stage = current_user_state_obj.stage
    current_brand_id = current_user_state_obj.current_brand_id
    
    if getattr(current_user_state_obj, "session_explicitly_ended", False):
        # Si la sesión fue terminada con el comando de salida, resetear al menú de selección de marcas
        # independientemente del estado en que se encuentre
        
        # Reiniciamos el flag para permitir una nueva conversación
        await update_user_state_db(db_session, current_user_state_obj, {"session_explicitly_ended": False})
        
        # Resetear al estado de selección de marca
        await reset_user_to_brand_selection(db_session, current_user_state_obj)
        
        logger.info(f"Usuario {user_key} envió mensaje después de finalizar sesión: '{user_input_text}'. Mostrando menú de selección de marcas.")
        
        # Enviamos el menú de selección de marcas
        selection_message = await get_company_selection_message(db_session, current_user_state_obj)
        await send_whatsapp_message(from_phone, selection_message)
        
        return {"status": "success", "action": "brand_selection_shown_after_session_end"}

    normalized_input_lower = user_input_text.lower()

    # Detectar comando de salida (terminar completamente la conversación)
    if any(keyword in normalized_input_lower for keyword in EXIT_KEYWORDS):
        if current_brand_id:
            company_obj = await get_company_by_id(db_session, current_brand_id)
            if company_obj:
                brand_name = company_obj.name
                normalized_brand_name = normalize_brand_name(brand_name)
                brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default"))
                
                # Obtener mensaje de despedida personalizado del perfil de marca
                farewell_message = brand_profile.get("farewell_message", None)
                
                # Si no hay mensaje personalizado en el perfil o es None, usar uno humanizado genérico
                if not farewell_message:
                    # Personalizar con el nombre del usuario si está disponible
                    user_name_part = f", {current_user_state_obj.collected_name.split()[0]}" if current_user_state_obj.collected_name else ""
                    # Variantes de despedida para agregar variabilidad natural
                    farewell_variants = [
                        f"¡Gracias por tu tiempo{user_name_part}! Ha sido un gusto poder asistirte desde {brand_name}. ¡Que tengas un excelente día! 👋",
                        f"¡Hasta pronto{user_name_part}! En {brand_name} quedamos a tu disposición para cuando nos necesites nuevamente. ¡Cuídate! ✨",
                        f"¡Ha sido un placer conversar contigo{user_name_part}! Recuerda que en {brand_name} estamos para ayudarte siempre que lo necesites. ¡Hasta la próxima! 👋"
                    ]
                    # Seleccionar aleatoriamente una variante para que parezca más natural
                    import random
                    farewell_message = random.choice(farewell_variants)
                
                # Enviar mensaje de despedida personalizado
                await send_whatsapp_message(from_phone, farewell_message)
                
                # Registrar en el log con más detalle para mejor trazabilidad
                logger.info(f"Usuario {user_key} terminó la conversación con '{user_input_text}'. Mensaje de despedida enviado: '{farewell_message[:50]}...'")
                
                # Marcar la sesión como explícitamente terminada en lugar de resetear al menú
                await update_user_state_db(db_session, current_user_state_obj, {"session_explicitly_ended": True})
                return {"status": "success", "action": "conversation_completely_ended", "brand_id": current_brand_id}
        
        # Si no hay marca actual, enviar un mensaje de despedida más natural y empático
        # Personalizar con el nombre del usuario si está disponible
        user_name_part = f", {current_user_state_obj.collected_name.split()[0]}" if current_user_state_obj.collected_name else ""
        farewell_message = f"¡Gracias por escribirnos{user_name_part}! Ha sido un placer ayudarte. Si necesitas cualquier cosa en el futuro, ¡estaremos aquí para ti! ¡Hasta pronto! 👋"
        await send_whatsapp_message(from_phone, farewell_message)
        await update_user_state_db(db_session, current_user_state_obj, {"session_explicitly_ended": True})
        logger.info(f"Usuario {user_key} terminó conversación sin marca seleccionada. Mensaje de despedida enviado.")
        return {"status": "success", "action": "conversation_completely_ended_no_brand"}
    
    # Detectar comandos para mostrar menú o reiniciar (mantiene el comportamiento original)
    if any(keyword in normalized_input_lower for keyword in RESET_KEYWORDS):
        if current_brand_id:
            company_obj = await get_company_by_id(db_session, current_brand_id)
            if company_obj:
                brand_name = company_obj.name
                normalized_brand_name = normalize_brand_name(brand_name)
                brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default"))
                
                # Mensaje para comandos de menú/reinicio
                reset_message = f"Volviendo al menú principal. ¿En qué más puedo ayudarte?"
                
                # Enviar mensaje de reinicio
                await send_whatsapp_message(from_phone, reset_message)
                
                # Registrar en el log
                logger.info(f"Usuario {user_key} solicitó reiniciar o mostrar menú con '{user_input_text}'")
        
        # Resetear el estado del usuario al menú de selección de marca
        await reset_user_to_brand_selection(db_session, current_user_state_obj)
        selection_message = await get_company_selection_message(db_session, current_user_state_obj)
        await send_whatsapp_message(from_phone, selection_message)
        return {"status": "success", "action": "reset_to_brand_selection_by_keyword"}

    if any(keyword in normalized_input_lower for keyword in OPT_OUT_KEYWORDS):
        # (Lógica de opt-out se mantiene)
        await update_user_subscription_status(db_session, from_phone, platform_name, False)
        await send_whatsapp_message(from_phone, "Has sido dado de baja...")
        return {"status": "success", "action": "unsubscribed_by_keyword"}
        
    if any(keyword in normalized_input_lower for keyword in OPT_IN_KEYWORDS):
        # (Lógica de opt-in se mantiene)
        await update_user_subscription_status(db_session, from_phone, platform_name, True)
        await send_whatsapp_message(from_phone, "¡Bienvenido de nuevo!...")
        return {"status": "success", "action": "subscribed_by_keyword"}
    
    await add_to_conversation_history(db_session, from_phone, platform_name, "user", user_input_text)
    
    current_stage = current_user_state_obj.stage
    current_brand_id = current_user_state_obj.current_brand_id
    brand_name_display = "la marca seleccionada" # Placeholder, obtener de la DB si es posible
    if current_brand_id:
        company_obj = await get_company_by_id(db_session, current_brand_id)
        if company_obj:
            brand_name_display = company_obj.name

    logger.info(f"Usuario {user_key} en etapa: {current_stage}, Marca ID: {current_brand_id}, Input: '{user_input_text}'")

    # --- Flujo Principal de la Conversación ---
    if current_stage == STAGE_SELECTING_BRAND:
        company_id_selected = await get_company_id_by_selection(db_session, user_input_text)
        if company_id_selected:
            await update_user_state_db(db_session, current_user_state_obj, {
                "current_brand_id": company_id_selected,
                "stage": STAGE_AWAITING_ACTION # Transición a la espera de acción
            })
            # Obtener el nombre de la compañía seleccionada
            company = await get_company_by_id(db_session, company_id_selected)
            company_name = company.name if company else None
            
            action_message_payload = await get_action_selection_message(
                company_name=company_name,  # Pasar el nombre de la compañía
                user_state_obj=current_user_state_obj
            )
            message_text_to_send = action_message_payload.get("text", "Error: Mensaje de acción no encontrado.")
            buttons_to_send = action_message_payload.get("buttons", [])
            await send_whatsapp_message(from_phone, message_text_to_send, buttons_to_send)
            return {"status": "success", "action": "brand_selected", "brand_id": company_id_selected}
        else:
            selection_message_text = await get_company_selection_message(db_session, current_user_state_obj)
            await send_whatsapp_message(from_phone, f"Opción no reconocida. Por favor, selecciona una opción válida de la lista:\n\n{selection_message_text}")
            return {"status": "success", "action": "invalid_brand_selection_retry"}

    elif current_stage == STAGE_AWAITING_ACTION:
        if not current_brand_id: # Seguridad: si no hay marca, volver a seleccionar
            logger.warning(f"Usuario {user_key} en STAGE_AWAITING_ACTION sin current_brand_id. Reseteando.")
            await reset_user_to_brand_selection(db_session, current_user_state_obj) #... (enviar mensaje de selección)
            return {"status": "error", "action": "reset_missing_brand_in_awaiting_action"}

        # Priorizar ID del botón si fue presionado
        if button_id_pressed == "action_schedule": # ID del botón "🗓️ Agendar Cita"
            logger.info(f"Usuario {user_key} seleccionó Agendar Cita (botón action_schedule).")
            # Iniciamos el flujo de recolección de datos para el agendamiento
            # Primero pedimos el nombre
            await update_user_state_db(db_session, current_user_state_obj, {
                "stage": STAGE_COLLECTING_NAME,
                "purpose_of_inquiry": user_input_text # Guardar el título del botón como propósito inicial
            })
            await send_whatsapp_message(from_phone, f"Para agendar tu cita con *{brand_name_display}*, necesito algunos datos. \n\nPor favor, escribe tu nombre completo:")
            return {"status": "success", "action": "transition_to_collecting_name_for_appointment"}

        elif button_id_pressed == "action_rag": # ID del botón "📚 Consultar información"
            logger.info(f"Usuario {user_key} seleccionó Consultar información (botón action_rag). Iniciando transición a RAG.")
        
            # Agregamos al usuario a la caché de transiciones pendientes ANTES de la actualización
            _pending_rag_transitions.add(user_key)
            logger.info(f"DIAGNÓSTICO-RAG: Usuario {user_key} añadido a caché de transiciones RAG pendientes. Estado actual: {current_user_state_obj.stage}")
        
            # Actualizamos el estado en la base de datos
            try:
                old_stage = current_user_state_obj.stage
                await update_user_state_db(db_session, current_user_state_obj, {"stage": STAGE_AWAITING_QUERY_FOR_RAG})
            
                # Verificación extra: asegurarnos que el cambio se reflejó en el objeto
                if current_user_state_obj.stage == STAGE_AWAITING_QUERY_FOR_RAG:
                    logger.info(f"Transición exitosa para usuario {user_key} de {old_stage} a {current_user_state_obj.stage}")
                else:
                    logger.warning(f"¡ALERTA! La actualización de estado para usuario {user_key} no se reflejó en el objeto. Sigue en: {current_user_state_obj.stage}")
            except Exception as e_update:
                logger.error(f"DIAGNÓSTICO-RAG: Error al actualizar estado para usuario {user_key}: {e_update}", exc_info=True)
                # Si hay error, eliminamos al usuario de la caché de transiciones pendientes
                if user_key in _pending_rag_transitions:
                    _pending_rag_transitions.remove(user_key)
                    logger.info(f"DIAGNÓSTICO-RAG: Usuario {user_key} eliminado de caché de transiciones debido a error en actualización")
        
            # Enviamos mensaje de bienvenida al flujo RAG
            await send_whatsapp_message(from_phone, f"¡Claro! Estoy aquí para ayudarte con tu consulta sobre *{brand_name_display}*. ¿Qué te gustaría saber?")
            return {"status": "success", "action": "transitioned_to_awaiting_query_for_rag"}

        elif button_id_pressed == "action_reset_menu": # ID del botón para volver al menú principal
            logger.info(f"Usuario {user_key} seleccionó Volver al Menú (botón action_reset_menu).")
            await reset_user_to_brand_selection(db_session, current_user_state_obj)
            selection_message = await get_company_selection_message(db_session, current_user_state_obj)
            await send_whatsapp_message(from_phone, selection_message)
            return {"status": "success", "action": "reset_to_brand_selection_from_action_menu"}
        
        else: # No se presionó un botón conocido, o fue texto libre. Intentar interpretar como chat.
            logger.info(f"Usuario {user_key} en STAGE_AWAITING_ACTION envió texto libre: '{user_input_text}'. Se tratará como inicio de RAG.")
            await update_user_state_db(db_session, current_user_state_obj, {"stage": STAGE_MAIN_CHAT_RAG})
            # Re-llamar a esta misma función (o una subfunción) para que procese el input bajo STAGE_MAIN_CHAT_RAG
            # Esto es un poco recursivo, considera una estructura de bucle o una llamada directa a la lógica de RAG.
            # Para simplicidad, podemos asumir que la siguiente iteración del webhook lo manejará si la UI es rápida,
            # o directamente llamar a la lógica de RAG aquí.
            # Vamos a intentar procesarlo directamente como si fuera STAGE_MAIN_CHAT_RAG:
            # --- COPIAR/PEGAR O REFACTORIZAR LÓGICA DE STAGE_MAIN_CHAT_RAG AQUÍ ---
            # O, más limpio, preparar el mensaje de "Estoy listo para tu consulta" y dejar que el siguiente mensaje active RAG.
            await send_whatsapp_message(from_phone, f"Entendido. Puedes hacerme tu consulta sobre *{brand_name_display}*.")
            return {"status": "success", "action": "text_in_awaiting_action_treated_as_rag_prompt"}


    elif current_stage == STAGE_AWAITING_QUERY_FOR_RAG:
        logger.info(f"Usuario {user_key} en estado STAGE_AWAITING_QUERY_FOR_RAG. Procesando consulta: '{user_input_text}'")

        if not current_brand_id:
            logger.warning(f"Usuario {user_key} en STAGE_AWAITING_QUERY_FOR_RAG sin current_brand_id. Reseteando.")
            await reset_user_to_brand_selection(db_session, current_user_state_obj)
            selection_message = await get_company_selection_message(db_session, current_user_state_obj)
            await send_whatsapp_message(from_phone, selection_message)
            return {"status": "error", "action": "reset_missing_brand_in_awaiting_query_for_rag"}
                # Detectar intención de agendamiento
        company_obj = await get_company_by_id(db_session, current_brand_id)
        if company_obj and detect_scheduling_intent(user_input_text):
            logger.info(f"Usuario {user_key} expresó intención de agendamiento en STAGE_AWAITING_QUERY_FOR_RAG: '{user_input_text}'")
            
            # Usar el enlace general de agendamiento de la configuración
            if settings.CALENDLY_GENERAL_SCHEDULING_LINK:
                # Personalizar con el nombre del usuario si disponible
                user_name_greeting = f", {current_user_state_obj.collected_name.split()[0]}" if current_user_state_obj.collected_name else ""
                
                # Obtener información del perfil de marca si está disponible
                brand_name = company_obj.name
                normalized_brand_name = normalize_brand_name(brand_name)
                brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default"))
                
                # Mensaje humanizado y personalizado para agendar cita con variantes para mayor naturalidad
                scheduling_variants = [
                    f"¡Por supuesto{user_name_greeting}! Estaremos encantados de coordinar una cita con *{brand_name}*. \n\nAquí tienes el enlace para que elijas el horario que mejor te funcione:\n\n{settings.CALENDLY_GENERAL_SCHEDULING_LINK}\n\nUna vez que confirmes tu cita, recibirás un correo de confirmación con todos los detalles. ¿Te puedo ayudar con algo más?",
                    
                    f"¡Genial{user_name_greeting}! Vamos a agendar esa reunión con *{brand_name}*. \n\nPuedes seleccionar el día y hora que prefieras en este enlace:\n\n{settings.CALENDLY_GENERAL_SCHEDULING_LINK}\n\nDespués de agendar, te enviaremos la confirmación por correo electrónico. Si tienes cualquier duda adicional, estoy aquí para ayudarte.",
                    
                    f"Me alegra poder ayudarte con tu cita{user_name_greeting}. \n\nPara coordinar una reunión con *{brand_name}*, utiliza este enlace y elige el horario que mejor se adapte a tu agenda:\n\n{settings.CALENDLY_GENERAL_SCHEDULING_LINK}\n\nLuego de confirmar tu cita, te llegará un correo con toda la información. ¿Necesitas algo más?"
                ]
                
                # Seleccionar aleatoriamente una variante para más naturalidad
                import random
                scheduling_message = random.choice(scheduling_variants)
                
                # Agregar mensaje de despedida si el perfil lo incluye
                await send_whatsapp_message(from_phone, scheduling_message)
                logger.info(f"Mensaje de agendamiento personalizado enviado a usuario {user_key} para marca {brand_name}")
                return {"status": "success", "action": "scheduling_link_sent", "brand_id": current_brand_id}
            else:
                logger.warning(f"Intención de agendamiento detectada pero no hay URL de agendamiento configurada en las variables de entorno")
                # Si no hay URL, dar respuesta más útil en lugar de ignorar
                await send_whatsapp_message(from_phone, f"Entiendo que quieres agendar una reunión con *{company_obj.name}*. Por favor, escribe 'agendar cita' para que pueda ayudarte con el proceso completo de agendamiento.")
                return {"status": "success", "action": "scheduling_intent_no_url"}  
        # Verificar palabras clave para salir de la conversación
        normalized_input = user_input_text.lower().strip()
        if any(keyword in normalized_input for keyword in settings.EXIT_CONVERSATION_KEYWORDS):
            logger.info(f"Usuario {user_key} utilizó palabra clave de salida: '{user_input_text}'")
            
            # Obtener el mensaje de despedida personalizado según la marca
            company_obj = await get_company_by_id(db_session, current_brand_id)
            if company_obj:
                brand_name = company_obj.name
                # Normalizar el nombre de la marca para buscar en BRAND_PROFILES
                normalized_brand_name = normalize_brand_name(brand_name)
                brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default"))
                
                # Obtener el mensaje de despedida personalizado o usar un mensaje genérico
                farewell_message = brand_profile.get("farewell_message", 
                    "¡Gracias por tu consulta! Si necesitas más información, estaré aquí. ¡Hasta pronto! 👋")
                
                # Enviar mensaje de despedida
                await send_whatsapp_message(from_phone, farewell_message)
                
                # No registrar este mensaje como una consulta para el historial
                # (Ya fue agregado antes, así que lo removemos)
                remove_last_user_message_from_history(user_key)
                
                # Resetear estado del usuario a selección de marca
                await reset_user_to_brand_selection(db_session, current_user_state_obj)
                
                return {"status": "success", "action": "conversation_exit_farewell_sent"}
        
        # Verificar palabras clave para reinicio
        if user_input_text.lower().strip() in RESET_KEYWORDS:
            await reset_user_to_brand_selection(db_session, current_user_state_obj)
            selection_message = await get_company_selection_message(db_session, current_user_state_obj)
            await send_whatsapp_message(from_phone, selection_message)
            return {"status": "success", "action": "reset_to_brand_selection_from_reset_keyword_in_awaiting_query_for_rag"}

        # Procesar la consulta RAG
        await add_to_conversation_history(db_session, from_phone, platform_name, "user", user_input_text)

        normalized_brand_name_for_rag = normalize_brand_name(brand_name_display)
        # La corrección para Javier Bazán y otros casos especiales ya se maneja
        # directamente en la función normalize_brand_name

        conversation_history = await get_conversation_history(db_session, from_phone, platform_name)

        # Obtener la instancia del retriever del estado de la aplicación
        retriever_instance = request.app.state.retriever
        if not retriever_instance:
            logger.error("No se pudo obtener la instancia del retriever del estado de la aplicación")
            await send_whatsapp_message(from_phone, "Lo siento, estoy teniendo dificultades para buscar información en este momento. Por favor, intenta de nuevo más tarde o escribe 'menu' para volver al menú principal.")
            return {"status": "error", "message": "Error interno: componente de búsqueda no disponible"}

        # Usar la función search_relevant_documents con el retriever
        relevant_docs = await search_relevant_documents(
            retriever_instance=retriever_instance,
            user_query=user_input_text,
            target_brand=normalized_brand_name_for_rag,
            k_final=getattr(settings, "RAG_NUM_DOCS_TO_RETRIEVE", 3)
        )
        context_from_docs = format_context_from_docs(relevant_docs)
        
        # Log del contexto RAG para verificación
        logger.info(f"CONTEXTO_RAG_PARA_LLM: '''{context_from_docs}'''")

        # Construir el prompt para el LLM - usando brand_name_display para acceder al perfil correcto
        full_prompt = build_llm_prompt(
            brand_name=brand_name_display, # Nombre legible de la marca en lugar del normalizado
            user_query=user_input_text,
            context=context_from_docs,
            conversation_history=conversation_history,
            user_collected_name=current_user_state_obj.collected_name if current_user_state_obj else None,
            # Detectar automáticamente si es primera interacción
            is_first_turn=(current_stage == STAGE_AWAITING_QUERY_FOR_RAG)
        )

        try:
            # Obtener respuesta del LLM
            # Obtener el cliente HTTP para LLM desde el estado de la aplicación

            llm_http_client = request.app.state.llm_http_client

            if not llm_http_client:

                logger.error(f"Error crítico: Cliente HTTP para LLM no disponible en app.state para usuario {user_key}")

                await send_whatsapp_message(from_phone, "Lo siento, estoy experimentando problemas técnicos. Por favor, intenta más tarde o escribe 'menú' para otras opciones.")

                return {"status": "error", "action": "llm_http_client_not_available"}

                

            # Obtener respuesta del LLM pasando explícitamente el cliente HTTP

            llm_api_response = await get_llm_response(full_prompt, http_client=llm_http_client)
            
            # Mensaje predeterminado en caso de error
            bot_response = "No pude generar una respuesta en este momento. ¿Podrías intentar reformular tu pregunta o escribir 'menú' para otras opciones?"
            
            # Validar que la respuesta sea válida
            if llm_api_response and isinstance(llm_api_response, str) and len(llm_api_response.strip()) > 0:
                bot_response = llm_api_response.strip()
                logger.info(f"RAG: Respuesta válida generada para {user_key}")
            else:
                logger.warning(f"RAG: Respuesta LLM inválida para {user_key}: '{llm_api_response}'")
                
            # Enviar respuesta al usuario
            await send_whatsapp_message(from_phone, bot_response)
            
            # Agregar a historial con timestamp
            await add_to_conversation_history(db_session, from_phone, platform_name, "assistant", bot_response, include_timestamp=True)
            
            # Actualizar estado del usuario para permitir conversación continua
            await update_user_state_db(db_session, current_user_state_obj, {
                "stage": STAGE_MAIN_CHAT_RAG,
                "last_interaction_at": datetime.now(timezone.utc)
            })
            
            # Log claro de la transición
            logger.info(f"RAG: Transición completada para {user_key}: {current_stage} → {STAGE_MAIN_CHAT_RAG}")
            
            return {"status": "success", "action": "rag_response_sent_transition_to_main_chat_rag"}
            
        except Exception as e_llm:
            logger.error(f"Error LLM para {user_key}: {e_llm}", exc_info=True)
            
            # Mensaje más específico según el tipo de error
            if "timeout" in str(e_llm).lower():
                fallback_message = "Estoy tardando más de lo esperado. ¿Podrías intentar con una pregunta más corta o específica?"
            elif "rate" in str(e_llm).lower():
                fallback_message = "Hay mucha demanda en este momento. Por favor, intenta nuevamente en unos segundos."
            else:
                fallback_message = "Lo siento, no pude procesar tu consulta. Por favor, escribe 'menu' para volver al menú principal."
                
            await send_whatsapp_message(from_phone, fallback_message)
            return {"status": "error", "action": "llm_error_in_awaiting_query_for_rag"}
            
    elif current_stage == STAGE_COLLECTING_NAME:
        # Validar y guardar el nombre del usuario
        if not user_input_text or len(user_input_text.strip()) < 3:
            await send_whatsapp_message(from_phone, "Por favor, proporciona tu nombre completo (al menos 3 caracteres).")
            return {"status": "error", "action": "invalid_name_for_appointment"}
        
        # Guardar el nombre y pasar al siguiente estado (recolectar propósito)
        await update_user_state_db(db_session, current_user_state_obj, {
            "collected_name": user_input_text.strip(),
            "stage": STAGE_COLLECTING_PURPOSE
        })
        
        # Si ya tenemos un propósito del botón, podemos saltar este paso
        if current_user_state_obj.purpose_of_inquiry and not current_user_state_obj.purpose_of_inquiry.startswith("🗓️"):
            # Ya tenemos un propósito válido, pasar a recolectar email
            await update_user_state_db(db_session, current_user_state_obj, {"stage": STAGE_COLLECTING_EMAIL})
            await send_whatsapp_message(from_phone, f"Gracias {user_input_text.strip().split()[0]}. ¿Cuál es tu correo electrónico?")
            return {"status": "success", "action": "name_saved_skip_purpose_for_appointment"}
        else:
            # Necesitamos preguntar el propósito
            await send_whatsapp_message(from_phone, f"Gracias {user_input_text.strip().split()[0]}. ¿Cuál es el propósito de tu cita?")
            return {"status": "success", "action": "name_saved_transition_to_purpose_for_appointment"}
            
    elif current_stage == STAGE_COLLECTING_PURPOSE:
        # Validar y guardar el propósito de la cita
        if not user_input_text or len(user_input_text.strip()) < 3:
            await send_whatsapp_message(from_phone, "Por favor, describe brevemente el propósito de tu cita.")
            return {"status": "error", "action": "invalid_purpose_for_appointment"}
        
        # Guardar el propósito y pasar a recolectar email
        await update_user_state_db(db_session, current_user_state_obj, {
            "purpose_of_inquiry": user_input_text.strip(),
            "stage": STAGE_COLLECTING_EMAIL
        })
        
        # Pedir el correo electrónico
        first_name = current_user_state_obj.collected_name.split()[0] if current_user_state_obj.collected_name else ""  
        await send_whatsapp_message(from_phone, f"Gracias {first_name}. ¿Cuál es tu correo electrónico?")
        return {"status": "success", "action": "purpose_saved_transition_to_email_for_appointment"}
        
    elif current_stage == STAGE_COLLECTING_EMAIL:
        # Validar y guardar el correo electrónico
        if not local_validators.is_valid_email(user_input_text.strip()):
            await send_whatsapp_message(from_phone, "Por favor, proporciona un correo electrónico válido.")
            return {"status": "error", "action": "invalid_email_for_appointment"}
        
        # Guardar el email y pasar a recolectar teléfono
        await update_user_state_db(db_session, current_user_state_obj, {
            "collected_email": user_input_text.strip(),
            "stage": STAGE_COLLECTING_PHONE
        })
        
        # Pedir el número de teléfono
        first_name = current_user_state_obj.collected_name.split()[0] if current_user_state_obj.collected_name else ""
        await send_whatsapp_message(from_phone, f"Gracias {first_name}. Por último, ¿cuál es tu número de teléfono de contacto? (Puede ser este mismo número u otro diferente)")
        return {"status": "success", "action": "email_saved_transition_to_phone_for_appointment"}
        
    elif current_stage == STAGE_COLLECTING_PHONE:
        # Validar y guardar el teléfono
        phone = user_input_text.strip()
        
        # Validación mejorada del número de teléfono
        digits = ''.join(filter(str.isdigit, phone))
        
        # Criterios de validación:
        # 1. Debe contener dígitos
        # 2. La longitud debe estar entre 8 y 15 dígitos (estándar internacional)
        # 3. No debe contener solo el mismo dígito repetido (ej: 999999999)
        if not digits:
            await send_whatsapp_message(from_phone, "Por favor, ingresa un número telefónico que contenga dígitos.")
            return {"status": "error", "action": "invalid_phone_no_digits"}
        elif len(digits) < 8 or len(digits) > 15:
            await send_whatsapp_message(from_phone, "Por favor, ingresa un número telefónico válido (entre 8 y 15 dígitos).")
            return {"status": "error", "action": "invalid_phone_length"}
        elif len(set(digits)) == 1 and len(digits) >= 8:  # Todos los dígitos son iguales
            await send_whatsapp_message(from_phone, "El número telefónico no parece válido. Por favor, verifica e intenta nuevamente.")
            return {"status": "error", "action": "invalid_phone_repeated_digits"}
        
        # Guardar el teléfono y pasar a mostrar información de agendamiento
        await update_user_state_db(db_session, current_user_state_obj, {
            "collected_phone": phone,
            "stage": STAGE_PROVIDING_SCHEDULING_INFO
        })
        
        # Mostrar información de agendamiento
        scheduling_response_msg = await _handle_providing_scheduling_info(db_session, current_user_state_obj, current_brand_id)
        if scheduling_response_msg:
            await send_whatsapp_message(from_phone, scheduling_response_msg)
        
        # Después de mostrar la info, transicionar a chat RAG para preguntas de seguimiento
        await update_user_state_db(db_session, current_user_state_obj, {"stage": STAGE_MAIN_CHAT_RAG})
        return {"status": "success", "action": "all_data_collected_scheduling_info_provided"}
        
    elif current_stage == STAGE_PROVIDING_SCHEDULING_INFO:
        # Este estado ahora significa que ya se mostró la info de Calendly.
        # Cualquier mensaje aquí podría ser un "gracias", una pregunta de seguimiento, o una nueva consulta.
        # Lo trataremos como una entrada para el chat RAG.
        logger.info(f"Usuario {user_key} en STAGE_PROVIDING_SCHEDULING_INFO (post-display). Mensaje: '{user_input_text}'. Transicionando a RAG.")
        await update_user_state_db(db_session, current_user_state_obj, {"stage": STAGE_MAIN_CHAT_RAG})
        # La lógica de STAGE_MAIN_CHAT_RAG se encargará de este mensaje en la "siguiente" iteración o si la llamamos.
        # Para evitar complejidad, asumimos que el siguiente webhook request con este mismo mensaje y el nuevo estado STAGE_MAIN_CHAT_RAG lo procesará.
        # Alternativamente, podrías duplicar la lógica de RAG aquí.
        # Por ahora, solo cambiamos el estado y enviamos un mensaje genérico si es la primera vez que entra aquí después de agendar.
        # Si el `purpose_of_inquiry` todavía está con el texto de agendar, significa que es la primera vez.
        if current_user_state_obj.purpose_of_inquiry and \
           (current_user_state_obj.purpose_of_inquiry.startswith("🗓️") or "agendar" in current_user_state_obj.purpose_of_inquiry.lower()):
            await update_user_state_db(db_session, current_user_state_obj, {"purpose_of_inquiry": "Seguimiento de agendamiento o nueva consulta"}) # Limpiar propósito
        
        # Llamaremos directamente a la lógica de RAG como si el estado ya fuera STAGE_MAIN_CHAT_RAG
        # Esto evita esperar otro ciclo de webhook.
        # Esencialmente, el código de STAGE_MAIN_CHAT_RAG se ejecutaría aquí.
        # Para mantenerlo DRY, considera una función helper_process_rag_message.
        # Por ahora, para ilustrar, duplicaré la lógica esencial:
        if not current_brand_id:
             await reset_user_to_brand_selection(db_session, current_user_state_obj); return {"status": "error"} # ...
        
        # --- INICIO LÓGICA RAG (duplicada/refactorizada de abajo) ---
        normalized_brand_name_for_rag = normalize_brand_name(brand_name_display)
        conversation_history_str = get_conversation_history(user_key)
        system_prompt_template = BRAND_PROFILES.get(normalized_brand_name_for_rag, BRAND_PROFILES["default"])
        
        # Se corrigió la llamada a la función correcta de RAG
        relevant_docs = await search_relevant_documents(user_input_text, target_brand=normalized_brand_name_for_rag)
        context_from_docs = format_context_from_docs(relevant_docs)
        
        # Log del contexto RAG para verificación
        logger.info(f"CONTEXTO_RAG_PARA_LLM (desde STAGE_PROVIDING_SCHEDULING_INFO): '''{context_from_docs}'''")

        full_prompt = build_llm_prompt(
            brand_name=brand_name_display,  # Usar el nombre original para correcta selección de perfil
            user_query=user_input_text,
            context=context_from_docs,
            conversation_history=conversation_history_str,
            user_collected_name=current_user_state_obj.collected_name if current_user_state_obj else None,
            is_first_turn=True # Permitir saludo inicial cuando viene de scheduling
        )
        logger.debug(f"Prompt LLM (desde STAGE_PROVIDING_SCHEDULING_INFO) para {user_key}:\n{full_prompt[:500]}...")
        try:
            # Obtener el cliente HTTP para LLM desde el estado de la aplicación
            llm_http_client = request.app.state.llm_http_client
            if not llm_http_client:
                logger.error(f"Error crítico: Cliente HTTP para LLM no disponible en app.state para usuario {user_key}")
                await send_whatsapp_message(from_phone, "Problemas con IA. Intenta de nuevo o 'menú'.")
                return {"status": "error", "action": "llm_http_client_not_available"}
                
            # Obtener respuesta del LLM pasando explícitamente el cliente HTTP
            llm_api_response = await get_llm_response(full_prompt, http_client=llm_http_client)
            bot_response = llm_api_response or "No pude generar una respuesta. Intenta de nuevo."
            await send_whatsapp_message(from_phone, bot_response)
            await add_to_conversation_history(db_session, from_phone, platform_name, "assistant", bot_response)
            # Podría volver a STAGE_AWAITING_ACTION o quedarse en RAG. Dejémoslo en RAG.
            # await update_user_state_db(db_session, current_user_state_obj, {"stage": STAGE_AWAITING_ACTION}) 
        except Exception as e_llm:
            logger.error(f"Error LLM (desde STAGE_PROVIDING_SCHEDULING_INFO) para {user_key}: {e_llm}", exc_info=True)
            await send_whatsapp_message(from_phone, "Problemas con IA. Intenta de nuevo o 'menú'.")
        return {"status": "success", "action": "rag_response_after_scheduling_info"}
        # --- FIN LÓGICA RAG ---


    elif current_stage == STAGE_MAIN_CHAT_RAG:
        logger.info(f"Procesando mensaje para usuario {user_key} en estado STAGE_MAIN_CHAT_RAG: '{user_input_text}'")
        
        if not current_brand_id:
            logger.warning(f"Usuario {user_key} en STAGE_MAIN_CHAT_RAG sin current_brand_id. Reseteando.")
            await reset_user_to_brand_selection(db_session, current_user_state_obj)
            selection_message = await get_company_selection_message(db_session, current_user_state_obj)
            await send_whatsapp_message(from_phone, selection_message)
            return {"status": "error", "action": "reset_missing_brand_in_rag"}
            
        # Detectar intención de agendamiento
        company_obj = await get_company_by_id(db_session, current_brand_id)
        if company_obj and (_contains_scheduling_keywords(user_input_text) or detect_scheduling_intent(user_input_text)):
            logger.info(f"Usuario {user_key} expresó intención de agendamiento en STAGE_MAIN_CHAT_RAG: '{user_input_text}'")
            
            # Usar la misma lógica de obtención de enlaces que en _handle_providing_scheduling_info
            # para garantizar consistencia en todos los enlaces de agendamiento
            try:
                # Usar el nombre del perfil si está disponible
                name_for_calendly = current_user_state_obj.collected_name or "Invitado"
                email_for_calendly = current_user_state_obj.collected_email
                
                # Validar email si es requerido por Calendly
                if email_for_calendly and not local_validators.is_valid_email(email_for_calendly):
                    logger.warning(f"Email '{email_for_calendly}' no válido para {user_key}. No se usará para Calendly.")
                    email_for_calendly = None
                
                # Obtener el tipo de evento adecuado
                event_type_uri = settings.CALENDLY_EVENT_TYPE_URI
                
                # Generar el enlace personalizado
                scheduling_link_url = await get_scheduling_link(
                    event_type_uri,
                    name=name_for_calendly,
                    email=email_for_calendly
                )
                
                if scheduling_link_url and scheduling_link_url.strip():
                    logger.info(f"Enlace de Calendly generado para {user_key}: {scheduling_link_url}")
                    scheduling_message = f"¡Claro! Con gusto te ayudo a agendar. Puedes elegir un horario con *{company_obj.name}* aquí:\n\n{scheduling_link_url}\n\n¿Necesitas algo más?"
                    await send_whatsapp_message(from_phone, scheduling_message)
                    return {"status": "success", "action": "scheduling_link_sent_from_main_chat"}
                else:
                    # Intentar con el enlace general como respaldo
                    if hasattr(settings, "CALENDLY_GENERAL_SCHEDULING_LINK") and settings.CALENDLY_GENERAL_SCHEDULING_LINK:
                        scheduling_link_url = settings.CALENDLY_GENERAL_SCHEDULING_LINK
                        logger.info(f"Usando enlace general de Calendly para {user_key}: {scheduling_link_url}")
                        scheduling_message = f"¡Claro! Con gusto te ayudo a agendar. Puedes elegir un horario con *{company_obj.name}* aquí:\n\n{scheduling_link_url}\n\n¿Necesitas algo más?"
                        await send_whatsapp_message(from_phone, scheduling_message)
                        return {"status": "success", "action": "scheduling_link_sent_from_main_chat_general"}
            except Exception as e:
                logger.error(f"Error al generar enlace de Calendly para {user_key}: {str(e)}", exc_info=True)
                
            # En lugar de usar el enlace de la compañía como respaldo, siempre usar CALENDLY_GENERAL_SCHEDULING_LINK si está disponible
            if hasattr(settings, "CALENDLY_GENERAL_SCHEDULING_LINK") and settings.CALENDLY_GENERAL_SCHEDULING_LINK:
                scheduling_url = settings.CALENDLY_GENERAL_SCHEDULING_LINK
                logger.info(f"Usando el enlace general de agendamiento configurado en las variables de entorno: {scheduling_url}")
                scheduling_message = f"¡Claro! Con gusto te ayudo a agendar. Puedes elegir un horario con *{company_obj.name}* aquí:\n\n{scheduling_url}\n\n¿Necesitas algo más?"
                await send_whatsapp_message(from_phone, scheduling_message)
                return {"status": "success", "action": "scheduling_link_sent_from_env_variable"}
                
            # Si no hay ningún enlace disponible
            logger.warning(f"Intención de agendamiento detectada pero no se pudo obtener URL para {user_key}")
            await send_whatsapp_message(from_phone, f"Entiendo que deseas agendar una cita con {company_obj.name}. Por favor, comunícate directamente con ellos para coordinar una cita, ya que no tengo disponible un enlace de agendamiento en este momento.")
            return {"status": "partial_success", "action": "scheduling_intent_acknowledged_no_url"}
                
        # Detectar solicitud de información de contacto
        if company_obj and _contains_contact_info_keywords(user_input_text):
            logger.info(f"Usuario {user_key} solicitó información de contacto en STAGE_MAIN_CHAT_RAG: '{user_input_text}'")
            
            # Generar respuesta con información de contacto
            contact_info_message = await _handle_contact_info_request(db_session, current_brand_id)
            await send_whatsapp_message(from_phone, contact_info_message)
            
            # Añadir a la conversación para mantener el historial
            await add_to_conversation_history(db_session, from_phone, platform_name, "user", user_input_text)
            await add_to_conversation_history(db_session, from_phone, platform_name, "assistant", contact_info_message)
            
            return {"status": "success", "action": "contact_info_provided_from_main_chat"}
            
        # --- BLOQUE DE VERIFICACIÓN DE COMANDOS DE SALIDA ---
        # Normalizar la entrada para mejorar la detección de palabras clave (asegurarse que es minúsculas)
        normalized_input = user_input_text.lower().strip()
        
        # Verificar si el mensaje contiene palabras de salida
        if any(keyword in normalized_input for keyword in settings.EXIT_CONVERSATION_KEYWORDS):
            company_obj = await get_company_by_id(db_session, current_brand_id)
            if company_obj:
                brand_name = company_obj.name
                normalized_brand_name = normalize_brand_name(brand_name)
                brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default"))
                farewell_message = brand_profile.get("farewell_message", "Gracias por contactarnos. ¡Hasta luego!")
                await send_whatsapp_message(from_phone, farewell_message)
                remove_last_user_message_from_history(user_key)
                await reset_user_to_brand_selection(db_session, current_user_state_obj)
                return {"status": "success", "action": "conversation_exit_farewell_sent_from_main_chat_rag"}
        
        # Verificar si hay insultos o contenido inapropiado
        if contains_inappropriate_content(normalized_input):
            company_obj = await get_company_by_id(db_session, current_brand_id)
            company_name = company_obj.name if company_obj else "nuestra marca"
            polite_response = f"Entiendo tu frustración. Estoy aquí para ayudarte con información sobre {company_name}. ¿Puedo asistirte con algo más?"
            await send_whatsapp_message(from_phone, polite_response)
            remove_last_user_message_from_history(user_key)
            return {"status": "handled", "action": "inappropriate_content_handled"}
            
        # Continuar con procesamiento normal RAG
        exit_keywords_lower = [keyword.lower() for keyword in settings.EXIT_CONVERSATION_KEYWORDS]
        
        # Verificar si es un comando de salida (case insensitive y más flexible en la coincidencia)
        is_exit_command = False
        for keyword in exit_keywords_lower:
            if normalized_input == keyword or normalized_input.startswith(keyword + " "):
                is_exit_command = True
                logger.info(f"Usuario {user_key} utilizó comando de salida detectado: '{user_input_text}' -> '{keyword}'")
                break
                
        if is_exit_command:
            logger.info(f"Usuario {user_key} utilizó palabra clave de salida en chat RAG: '{user_input_text}'")
            
            # Obtener el mensaje de despedida personalizado según la marca
            company_obj = await get_company_by_id(db_session, current_brand_id)
            if company_obj:
                brand_name = company_obj.name
                # Normalizar el nombre de la marca para buscar en BRAND_PROFILES
                normalized_brand_name = normalize_brand_name(brand_name)
                brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default"))
                
                # Obtener el mensaje de despedida personalizado o usar un mensaje genérico
                farewell_message = brand_profile.get("farewell_message", 
                    "¡Gracias por su consulta! Ha sido un placer atenderle.\n\nLa conversación ha finalizado correctamente. Para iniciar una nueva consulta o seleccionar otra marca, simplemente envíe cualquier mensaje.\n\nQue tenga un excelente día. ¡Hasta pronto! 👋")
                
                # Enviar mensaje de despedida
                await send_whatsapp_message(from_phone, farewell_message)
                
                # No registrar este mensaje como una consulta para el historial
                # (Ya fue agregado antes, así que lo removemos)
                remove_last_user_message_from_history(user_key)
                
                # Marcar explícitamente que la sesión terminó
                await update_user_state_db(db_session, current_user_state_obj, {"session_explicitly_ended": True})
                logger.info(f"Usuario {user_key}: Marca de sesión finalizada (session_explicitly_ended = True)")
                
                # Resetear explicitamente el estado del usuario a selección de marca
                # Primero cambiamos stage directamente para evitar condición de carrera
                current_user_state_obj.stage = STAGE_SELECTING_BRAND
                
                # Ahora forzamos el reseteo completo con force=True (doble seguridad)
                await reset_user_to_brand_selection(db_session, current_user_state_obj, force=True)
                logger.info(f"Usuario {user_key}: Reseteo forzado del estado a selección de marca completado.")
                
                # Asegurar que el flujo termina aquí
                return {"status": "success", "action": "conversation_exit_completed_from_rag"}

        # Verificar palabras clave para reinicio
        if user_input_text.lower().strip() in RESET_KEYWORDS:
            logger.info(f"Usuario {user_key} solicitó reinicio con palabra clave: '{user_input_text}'")
            await reset_user_to_brand_selection(db_session, current_user_state_obj, force=True)
            selection_message = await get_company_selection_message(db_session, current_user_state_obj)
            await send_whatsapp_message(from_phone, selection_message)
            return {"status": "success", "action": "reset_to_brand_selection_from_reset_keyword_in_main_chat_rag"}
        
        # Verificar palabras clave para agendar cita
        normalized_input = user_input_text.lower().strip()
        scheduling_keywords = ["agendar", "cita", "calendario", "reservar", "hablar", "contactar", "comunicar", "reunion"]
        
        if any(keyword in normalized_input for keyword in scheduling_keywords):
            logger.info(f"Usuario {user_key} solicitó agendar cita con frase: '{user_input_text}'")
            
            # Obtener información de la compañía actual
            company_obj = await get_company_by_id(db_session, current_brand_id)
            # Verificar si existe una propiedad calendly_link en el perfil de marca
            brand_name = company_obj.name if company_obj else "default"
            normalized_brand_name = normalize_brand_name(brand_name)
            brand_profile = BRAND_PROFILES.get(normalized_brand_name, BRAND_PROFILES.get("default"))
            calendly_link = brand_profile.get("calendly_link")
            
            if calendly_link:
                # Crear mensaje con enlace de Calendly
                scheduling_message = f"¡Gracias por tu interés en agendar una cita! 📅\n\nPuedes hacerlo directamente a través del siguiente enlace:\n\n{calendly_link}\n\nUna vez agendada, recibirás una confirmación por correo electrónico. ¿Necesitas algo más?"
                
                # Enviar mensaje con el enlace
                await send_whatsapp_message(from_phone, scheduling_message)
                
                # Añadir al historial de conversación
                await add_to_conversation_history(db_session, from_phone, platform_name, "assistant", scheduling_message)
                
                return {"status": "success", "action": "scheduling_link_sent"}
            else:
                logger.warning(f"Usuario {user_key} solicitó agendar pero la compañía ID {current_brand_id} no tiene enlace de Calendly configurado")
                # Continuamos con el flujo normal para que el LLM responda adecuadamente
            
        # Verificar caché de transiciones pendientes para RAG
        if user_key in _pending_rag_transitions:
            logger.info(f"Usuario {user_key} estaba en caché de transiciones pendientes RAG. Forzando estado STAGE_MAIN_CHAT_RAG")
            current_user_state_obj.stage = STAGE_MAIN_CHAT_RAG
            # Eliminar de la caché ya que estamos procesando correctamente el mensaje
            _pending_rag_transitions.remove(user_key)
    
        # Añadir la consulta del usuario al historial de la conversación
        await add_to_conversation_history(db_session, from_phone, platform_name, "user", user_input_text)
        
        # Lógica de RAG / LLM
        normalized_brand_name_for_rag = normalize_brand_name(brand_name_display)
        # La corrección para Javier Bazán y otros casos especiales ya se maneja
        # directamente en la función normalize_brand_name
        conversation_history = await get_conversation_history(db_session, from_phone, platform_name)
        logger.info(f"Buscando documentos RAG para: '{user_input_text}' en marca '{normalized_brand_name_for_rag}'")
        
        # Obtener la instancia del retriever del estado de la aplicación
        retriever_instance = request.app.state.retriever
        if not retriever_instance:
            logger.error("No se pudo obtener la instancia del retriever del estado de la aplicación")
            return {"status": "error", "message": "Error interno: componente de búsqueda no disponible"}
            
        # Usar la función search_relevant_documents con el retriever
        relevant_docs = await search_relevant_documents(
            retriever_instance=retriever_instance,
            user_query=user_input_text,
            target_brand=normalized_brand_name_for_rag,
            k_final=getattr(settings, "RAG_NUM_DOCS_TO_RETRIEVE", 3)
        )
        context_from_docs = format_context_from_docs(relevant_docs)
        
        # Detectar si no hay suficiente contexto relevante
        has_relevant_context = bool(relevant_docs) and len(context_from_docs.strip()) > 50

        # Determinar si es primer turno basado en el historial de conversación
        is_first_interaction = not conversation_history or len(conversation_history) <= 2
        
        # Usar el nombre original de la marca para la búsqueda del perfil
        full_prompt = build_llm_prompt(
            brand_name=brand_name_display,  # Usar el nombre original, no el normalizado
            user_query=user_input_text,
            context=context_from_docs,
            conversation_history=conversation_history,
            user_collected_name=current_user_state_obj.collected_name if current_user_state_obj else None,
            is_first_turn=is_first_interaction # Determina dinámicamente si es primer turno
        )
        logger.debug(f"Prompt completo para LLM (usuario {user_key} en STAGE_MAIN_CHAT_RAG):\n{full_prompt[:500]}...") # Loggear solo una parte

        try:
            # Obtener respuesta del LLM
            # Obtener el cliente HTTP para LLM desde el estado de la aplicación

            llm_http_client = request.app.state.llm_http_client

            if not llm_http_client:

                logger.error(f"Error crítico: Cliente HTTP para LLM no disponible en app.state para usuario {user_key}")

                await send_whatsapp_message(from_phone, "Lo siento, estoy experimentando problemas técnicos. Por favor, intenta más tarde o escribe 'menú' para otras opciones.")

                return {"status": "error", "action": "llm_http_client_not_available"}

                

            # Si no hay contexto relevante, dar una respuesta más útil en lugar de generar respuesta genérica
            if not has_relevant_context:
                # Obtener el perfil de la marca para personalizar la respuesta
                company_obj = await get_company_by_id(db_session, current_brand_id)
                brand_name = company_obj.name if company_obj else "nuestra empresa"
                
                # Respuestas naturales y útiles cuando no se encuentra información específica
                alternative_options = [
                    f"¡Hola! Veo que estás interesado en saber más. Aunque no tengo los detalles específicos sobre eso, puedo contarte sobre los servicios y productos de {brand_name}. ¿Te gustaría que te cuente más sobre lo que ofrecemos?",
                    f"¡Gracias por tu consulta! Actualmente no tengo esa información a mano, pero estaré encantado de ayudarte con otros aspectos de {brand_name}. ¿Te gustaría saber sobre nuestros servicios, horarios de atención o cómo contactarnos?",
                    f"¡Interesante pregunta! Aunque no tengo esa información específica en este momento, puedo ayudarte con muchas otras consultas sobre {brand_name}. ¿Te gustaría que te cuente sobre nuestros productos destacados o servicios más populares?",
                    f"¡Hola! Me encantaría ayudarte con eso. Mientras actualizo mi base de conocimiento, ¿podrías contarme más sobre lo que necesitas? Mientras tanto, podría informarte sobre otros aspectos de {brand_name} que podrían ser de tu interés.",
                    f"Gracias por tu paciencia. Aunque no tengo la respuesta exacta ahora mismo, en {brand_name} valoramos mucho tus consultas. ¿Te gustaría que te ayude con información sobre nuestros servicios o que te ponga en contacto con un asesor especializado?"
                ]
                
                # Elegir aleatoriamente para dar variedad
                import random
                bot_response = random.choice(alternative_options)
                
                # Si el usuario ha recibido respuestas sin contexto varias veces seguidas, ofrecer reiniciar
                user_no_context_count = getattr(handle_whatsapp_message, f"_no_context_count_{user_key}", 0) + 1
                setattr(handle_whatsapp_message, f"_no_context_count_{user_key}", user_no_context_count)
                
                if user_no_context_count >= 2:
                    bot_response += "\n\nParece que estoy teniendo dificultades para responder a tus preguntas actuales. ¿Quieres reiniciar la conversación? Escribe 'reiniciar' o 'salir'."
                    setattr(handle_whatsapp_message, f"_no_context_count_{user_key}", 0)  # Reiniciar contador
            else:
                # Resetear contador de "sin contexto" si hay contexto
                setattr(handle_whatsapp_message, f"_no_context_count_{user_key}", 0)
                
                # Obtener respuesta del LLM pasando explícitamente el cliente HTTP
                llm_api_response = await get_llm_response(full_prompt, http_client=llm_http_client)
                
                bot_response = "No pude generar una respuesta en este momento. ¿Podrías intentar reformular tu pregunta o escribir 'menú' para otras opciones?"
                if llm_api_response:
                    bot_response = llm_api_response.strip()
            
            # Enviar respuesta al usuario
            await send_whatsapp_message(from_phone, bot_response)
            await add_to_conversation_history(db_session, from_phone, platform_name, "assistant", bot_response)
            
            # Decidir si después de una respuesta RAG vuelve a STAGE_AWAITING_ACTION o se queda en RAG.
            # Para una conversación fluida, es mejor quedarse en STAGE_MAIN_CHAT_RAG.
            # Si quieres que cada respuesta RAG termine y muestre el menú de acciones, cambia el estado:
            # await update_user_state_db(db_session, current_user_state_obj, {"stage": STAGE_AWAITING_ACTION})
            # logger.info(f"Usuario {user_key} respondió con RAG, volviendo a STAGE_AWAITING_ACTION.")
            
            # Si el proceso RAG fue exitoso y el usuario estaba en la caché de transiciones, eliminarlo
            if user_key in _pending_rag_transitions:
                _pending_rag_transitions.remove(user_key)
                logger.info(f"DIAGNÓSTICO-RAG: Usuario {user_key} procesado exitosamente en flujo RAG y eliminado de caché de transiciones")
                
                # Verificar estado en la DB para asegurar que todo está bien
                try:
                    verification_state = await db_session.get(UserState, (current_user_state_obj.user_id, current_user_state_obj.platform))
                    if verification_state and verification_state.stage == STAGE_MAIN_CHAT_RAG:
                        logger.info(f"DIAGNÓSTICO-RAG: Verificado estado final en DB para {user_key}: correctamente en STAGE_MAIN_CHAT_RAG")
                    else:
                        stage_in_db = verification_state.stage if verification_state else "desconocido"
                        logger.warning(f"DIAGNÓSTICO-RAG: Inconsistencia - Estado en DB para {user_key} es {stage_in_db}, no STAGE_MAIN_CHAT_RAG")
                except Exception as e_verify:
                    logger.error(f"DIAGNÓSTICO-RAG: Error al verificar estado final en DB para {user_key}: {e_verify}", exc_info=True)
            
            return {"status": "success", "action": "llm_rag_response_sent"}

        except Exception as e_llm:
            logger.error(f"Error al obtener respuesta del LLM para {user_key} en STAGE_MAIN_CHAT_RAG: {e_llm}", exc_info=True)
            await send_whatsapp_message(from_phone, "Lo siento, tuve problemas para procesar tu consulta con la IA en este momento. Por favor, intenta de nuevo más tarde o escribe 'menú'.")
            return {"status": "error", "source": "llm_call_in_rag_stage"}
            
    # Aquí irían los elif para STAGE_COLLECTING_NAME, STAGE_COLLECTING_EMAIL, STAGE_COLLECTING_PURPOSE
    # Ejemplo:
    # elif current_stage == STAGE_COLLECTING_NAME:
    #     # Validar y guardar nombre
    #     # Transicionar a STAGE_COLLECTING_EMAIL
    #     # Enviar mensaje pidiendo email

    else: # Estado desconocido o no manejado explícitamente
        logger.warning(f"Estado no reconocido o no manejado explícitamente: {current_stage} para usuario {user_key}. Reiniciando a selección de marca.")
        await reset_user_to_brand_selection(db_session, current_user_state_obj, force=True)
        selection_message = await get_company_selection_message(db_session, current_user_state_obj)
        await send_whatsapp_message(from_phone, f"Parece que nos perdimos un poco. Volvamos al inicio.\n\n{selection_message}")
        return {"status": "success", "action": "unhandled_stage_reset"}

async def process_webhook_payload(payload: dict, db_session: AsyncSession, request: Request):
    """
    Procesa el payload de un webhook de WhatsApp Business API.
    Implementa manejo completo de errores para asegurar respuestas 
    robustas incluso en caso de fallos.
    """
    request_id = f"req_{datetime.now(tz=timezone.utc).strftime('%Y%m%d%H%M%S')}_{id(request)}"
    logger.info(f"[{request_id}] process_webhook_payload: Recibido payload. Object Type: '{payload.get('object', 'N/A')}'")

    try:
        object_type = payload.get("object")
        if object_type != "whatsapp_business_account":
            logger.info(f"process_webhook_payload: Payload no es de 'whatsapp_business_account' (es '{object_type}'). Ignorando.")
            return

        try:
            data = WhatsAppPayload.model_validate(payload)
            logger.debug("process_webhook_payload: Payload validado exitosamente con WhatsAppPayload model.")
        except Exception as pydantic_error:
            logger.error(f"process_webhook_payload: Error de validación Pydantic: {pydantic_error}", exc_info=True)
            return

        if not data.entry:
            logger.info("process_webhook_payload: Payload sin 'entry'.")
            return

        for entry_item in data.entry:
            if not entry_item.changes: continue
            for change_item in entry_item.changes:
                value_item = change_item.value
                if not value_item: continue

                if value_item.statuses: # Manejo de statuses
                    # ... (tu código de manejo de status actual, se mantiene) ...
                    pass
                elif value_item.errors: # Manejo de errores
                    # ... (tu código de manejo de errores actual, se mantiene) ...
                    pass
                elif change_item.field == "messages" and value_item.messages:
                    logger.info(f"process_webhook_payload: {len(value_item.messages)} mensaje(s) entrante(s).")
                    for msg_obj_payload in value_item.messages:
                        user_profile_name_extracted: Optional[str] = None
                        if value_item.contacts and value_item.contacts[0] and value_item.contacts[0].profile:
                            user_profile_name_extracted = value_item.contacts[0].profile.name
                        
                        current_platform = "whatsapp"
                        
                        # Actualizar perfil del usuario si tenemos el nombre del webhook (asíncrono, no bloqueante)
                        if user_profile_name_extracted:
                           # asyncio.create_task(update_user_profile(db_session, msg_obj_payload.from_number, current_platform, user_profile_name_extracted))
                           # Lo hacemos directamente await si no es problemático para el tiempo de respuesta del webhook
                           await update_user_profile(db_session, msg_obj_payload.from_number, current_platform, user_profile_name_extracted)


                        # Control de mensajes duplicados - usar una colección en memoria para evitar reprocesar mensajes
                        # Esta colección se reinicia cuando se reinicia el servidor, pero evita duplicación durante la misma sesión
                        processed_msg_ids = getattr(process_webhook_payload, "_processed_msg_ids", set())
                        if msg_obj_payload.id in processed_msg_ids:
                            logger.warning(f"MENSAJE DUPLICADO DETECTADO Y BLOQUEADO: ID '{msg_obj_payload.id}' de '{msg_obj_payload.from_number}', Tipo '{msg_obj_payload.type}', Contenido: '{msg_obj_payload.text if msg_obj_payload.type == 'text' else 'contenido interactivo'}'")
                            continue
                            
                        # Limitar tamaño de la caché para evitar consumo excesivo de memoria
                        if len(processed_msg_ids) > 1000:  # Mantener últimos 1000 mensajes procesados
                            logger.info(f"Limpiando caché de mensajes procesados, tamaño actual: {len(processed_msg_ids)}")
                            processed_msg_ids.clear()
                            
                        # Marcar mensaje como procesado
                        processed_msg_ids.add(msg_obj_payload.id)
                        setattr(process_webhook_payload, "_processed_msg_ids", processed_msg_ids)
                        logger.info(f"Mensaje marcado como procesado: ID '{msg_obj_payload.id}'. Total en caché: {len(processed_msg_ids)}.")
                        
                        logger.debug(f"Procesando msg ID '{msg_obj_payload.id}' de '{msg_obj_payload.from_number}', Tipo '{msg_obj_payload.type}'.")

                        # Solo procesar tipos de mensajes que la lógica de estados puede manejar (texto o interactivos)
                        # Nota: Tu modelo WhatsAppMessage ya debería unificar 'button' legacy a 'interactive' si esa es la intención.
                        # El código anterior para convertir 'button' a 'interactive' se puede mantener si es necesario,
                        # o se asume que msg_obj_payload ya viene normalizado.
                        if msg_obj_payload.type in ['text', 'interactive']:
                            try:
                                await handle_whatsapp_message(
                                    msg_obj_payload, 
                                    user_profile_name_extracted, 
                                    current_platform, 
                                    db_session,
                                    request # Pasar request si es necesario para handle_whatsapp_message
                                )
                            except ValueError as e_val:
                                # Error de validación esperado
                                logger.warning(f"[{request_id}] Error de validación al procesar mensaje: {e_val}")
                                await send_whatsapp_message(
                                    to=msg_obj_payload.from_number, 
                                    message_payload="Lo siento, no pude procesar tu mensaje. Por favor, intenta de nuevo con un formato válido."
                                )
                            except Exception as e_msg:
                                # Error inesperado pero controlado
                                logger.error(f"[{request_id}] Error procesando mensaje: {e_msg}", exc_info=True)
                                await send_whatsapp_message(
                                    to=msg_obj_payload.from_number, 
                                    message_payload="Lo siento, estamos experimentando dificultades técnicas. Por favor, intenta de nuevo en unos momentos."
                                )
                        else:
                            logger.info(f"[{request_id}] Mensaje tipo '{msg_obj_payload.type}' de '{msg_obj_payload.from_number}' no procesado activamente. ID: {msg_obj_payload.id}")
                            # Enviar mensaje informando que este tipo no es soportado
                            await send_whatsapp_message(
                                to=msg_obj_payload.from_number, 
                                message_payload="Lo siento, actualmente no puedo procesar este tipo de mensaje. Por favor, envía un mensaje de texto."
                            )
                else:
                    logger.debug(f"ChangeItem no contiene statuses, errors, ni messages procesables. Field: {change_item.field}")

    except Exception as e_main_webhook_processing:
        logger.critical(f"[{request_id}] Error CRÍTICO en process_webhook_payload: {e_main_webhook_processing}", exc_info=True)
        
        # Intentar informar a admins, si es posible
        admin_notification_number = getattr(settings, 'ADMIN_NOTIFICATION_NUMBER', None)
        if admin_notification_number:
            try:
                error_message = f"Error en webhook (ID: {request_id}): {str(e_main_webhook_processing)[:100]}"
                await send_whatsapp_message(to=admin_notification_number, message_payload=error_message)
            except Exception as e_notify:
                logger.error(f"No se pudo notificar al admin sobre error: {e_notify}")
                
        # Estructura de respuesta para monitorización y debugging
        return {
            "status": "error",
            "request_id": request_id,
            "error_type": type(e_main_webhook_processing).__name__,
            "timestamp": datetime.now(tz=timezone.utc).isoformat()
        }