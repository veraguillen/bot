# app/main/state_manager.py
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timezone, timedelta # timedelta para expiración de caché

# Importar modelos SQLAlchemy
from app.models.user_state import UserState
from app.models.company_models import Company
from app.models.interaction_models import Interaction
from app.models.appointment_models import Appointment
from app.utils.logger import logger

# --- Constantes de Estados ---
STAGE_SELECTING_BRAND = "selecting_brand"
STAGE_AWAITING_ACTION = "awaiting_action_choice"
STAGE_AWAITING_QUERY_FOR_RAG = "awaiting_query_for_rag"  # Estado para recibir la consulta después de seleccionar "Consultar información"
STAGE_MAIN_CHAT_RAG = "main_chat_rag"
STAGE_CALENDLY_INITIATE = "calendly_initiate"  # Estado para iniciar proceso de agendamiento
STAGE_PROVIDING_SCHEDULING_INFO = "providing_scheduling_info"
STAGE_COLLECTING_NAME = "collecting_name"
STAGE_COLLECTING_EMAIL = "collecting_email"
STAGE_COLLECTING_PHONE = "collecting_phone"
STAGE_COLLECTING_PURPOSE = "collecting_purpose"

# --- Caché de Compañías ---
_company_cache: Optional[List[Company]] = None
_cache_last_loaded_at: Optional[datetime] = None
_CACHE_EXPIRATION_MINUTES = 60

async def get_all_companies(session: AsyncSession, use_cache: bool = True, force_reload_cache: bool = False) -> List[Company]:
    global _company_cache, _cache_last_loaded_at
    
    now = datetime.now(timezone.utc)
    cache_expired = False
    if _cache_last_loaded_at:
        if (now - _cache_last_loaded_at).total_seconds() > _CACHE_EXPIRATION_MINUTES * 60:
            cache_expired = True
            logger.info("Caché de compañías expirada.")

    if force_reload_cache or cache_expired:
        logger.info(f"get_all_companies: Forzando recarga de caché (force: {force_reload_cache}, expired: {cache_expired}).")
        _company_cache = None

    if use_cache and _company_cache is not None:
        logger.debug("Usando caché de compañías.")
        return _company_cache

    logger.info("Consultando compañías desde la DB...")
    stmt = select(Company).order_by(Company.id)
    result = await session.execute(stmt)
    companies_from_db = list(result.scalars().all())
    
    if companies_from_db:
        _company_cache = companies_from_db
        _cache_last_loaded_at = now
        logger.info(f"Se cargaron {len(companies_from_db)} compañías y se almacenaron en caché.")
    else:
        logger.warning("No se encontraron compañías en la DB.")
        _company_cache = []
        _cache_last_loaded_at = now
        
    return _company_cache

async def get_company_by_id(session: AsyncSession, company_id: Optional[int]) -> Optional[Company]:
    if company_id is None: return None
    await get_all_companies(session) # Asegura que caché esté poblada/fresca
    if _company_cache:
        for company_obj_cache in _company_cache:
            if company_obj_cache.id == company_id:
                 return company_obj_cache
    
    company_obj_db = await session.get(Company, company_id)
    if not company_obj_db: logger.warning(f"Compañía ID {company_id} NO encontrada en DB.")
    return company_obj_db

async def get_brand_name_by_id(session: AsyncSession, brand_id: Optional[int]) -> Optional[str]:
    if brand_id is None: return None
    company = await get_company_by_id(session, brand_id)
    return company.name if company else None

async def get_company_id_by_selection(session: AsyncSession, user_input: str) -> Optional[int]:
    normalized_input = user_input.strip().lower()
    companies = await get_all_companies(session)
    if not companies: return None

    if normalized_input.isdigit():
        try:
            option_number = int(normalized_input)
            if 1 <= option_number <= len(companies):
                return companies[option_number - 1].id
        except ValueError: pass

    company_map: Dict[str, int] = {comp.name.lower(): comp.id for comp in companies}
    # Añadir alias comunes
    for comp in companies:
        name_lower = comp.name.lower()
        if "fundaci" in name_lower: company_map["fundacion"] = comp.id
        if "ehecatl" in name_lower: company_map["ehecatl"] = comp.id
        if "bazan" in name_lower: company_map["bazan"] = comp.id; company_map["javier bazan"] = comp.id
        if "udd" in name_lower: company_map["udd"] = comp.id; company_map["universidad"] = comp.id
        if "fes" in name_lower: company_map["fes"] = comp.id; company_map["frente"] = comp.id
    
    # Buscar coincidencias con emojis numéricos (1️⃣, 2️⃣, etc.)
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    if user_input.strip() in number_emojis:
        idx = number_emojis.index(user_input.strip())
        if idx < len(companies):
            return companies[idx].id
            
    # Verificar si hay coincidencia directa con el nombre o un alias
    for key, value in company_map.items():
        if key in normalized_input or normalized_input in key:
            return value
            
    # Si no hay coincidencia exacta, intentar con get
    if company_map.get(normalized_input):
        return company_map.get(normalized_input)
    
    # Si no se encuentra ninguna coincidencia, devolver None
    return None

# --- Gestión de Estado y Suscripción del Usuario ---
async def get_or_create_user_state(db_session: AsyncSession, user_id: str, platform: str, display_name: Optional[str] = None) -> UserState:
    """
    ✨ Encuentra o crea un perfil de usuario personalizado.
    Usa la combinación mágica de (user_id, platform) como llave única.
    """
    stmt = select(UserState).filter_by(user_id=user_id, platform=platform)
    result = await db_session.execute(stmt)
    user_state = result.scalar_one_or_none()
    
    current_time_utc = datetime.now(timezone.utc)

    if user_state is None:
        logger.info(f"Nuevo UserState para {platform}:{user_id}. Creando...")
        user_state = UserState(
            user_id=user_id,
            platform=platform,
            collected_name=display_name,
            stage=STAGE_SELECTING_BRAND,
            is_subscribed=True,
            last_interaction_at=current_time_utc
        )
        db_session.add(user_state)
        try:
            await db_session.commit()
            await db_session.refresh(user_state)
            logger.info(f"Nuevo UserState creado y guardado para {platform}:{user_id}. ID: {user_state.id}, Stage: {user_state.stage}")
        except Exception as e:
            logger.error(f"Error al guardar nuevo UserState para {platform}:{user_id}: {e}", exc_info=True)
            await db_session.rollback()
            raise
    else:
        # Actualizar solo el timestamp y el nombre si es necesario
        user_state.last_interaction_at = current_time_utc
        if display_name and user_state.collected_name != display_name:
            user_state.collected_name = display_name
            db_session.add(user_state)
            try:
                await db_session.commit()
                logger.debug(f"Nombre de usuario actualizado para {platform}:{user_id}")
            except Exception as e:
                logger.error(f"Error al actualizar nombre de usuario {platform}:{user_id}: {e}", exc_info=True)
                await db_session.rollback()
        
        logger.debug(f"UserState existente para {platform}:{user_id}. Stage:'{user_state.stage}'. Timestamp actualizado.")
    
    return user_state

async def update_user_state_db(db_session: AsyncSession, user_state_obj: UserState, updates: Dict[str, Any]):
    """✨ Actualiza la magia detrás de escena para mantener fresca la experiencia del usuario."""
    updated_fields_log = {}
    changed_besides_timestamp = False
    user_key = f"{user_state_obj.platform}:{user_state_obj.user_id}"
    
    for key, value in updates.items():
        if hasattr(user_state_obj, key):
            current_value = getattr(user_state_obj, key)
            if current_value != value:
                setattr(user_state_obj, key, value)
                updated_fields_log[key] = value
                changed_besides_timestamp = True
        else:
            logger.warning(f"Intento de actualizar campo inexistente '{key}' en UserState para {user_key}.")
    
    user_state_obj.last_interaction_at = datetime.now(timezone.utc) # Asegurar que onupdate funcione o actualizar manualmente
    
    try:
        # Asegurar que obtenemos la referencia más reciente desde la DB
        db_user_state = await db_session.get(UserState, (user_state_obj.user_id, user_state_obj.platform))
        
        if db_user_state:
            # Actualizar también la referencia de DB directamente
            for key, value in updates.items():
                if hasattr(db_user_state, key):
                    setattr(db_user_state, key, value)
            db_user_state.last_interaction_at = user_state_obj.last_interaction_at
            
            # Marcar ambos objetos para actualización
            db_session.add(db_user_state)
        
        # En cualquier caso, marcar el objeto original también
        db_session.add(user_state_obj)
        
        # Forzar flush para asegurar persistencia inmediata
        await db_session.flush()
        
        # Intentar commit inmediato para mayor seguridad
        await db_session.commit()
        
        if changed_besides_timestamp:
            logger.info(f"UserState {user_key} actualizado y guardado en DB con: {updated_fields_log}")
            
            # Verificación adicional de diagnóstico
            if "stage" in updates and updates["stage"] == STAGE_MAIN_CHAT_RAG:
                # Verificar que el cambio a RAG se haya guardado correctamente
                verification = await db_session.get(UserState, (user_state_obj.user_id, user_state_obj.platform))
                if verification and verification.stage == STAGE_MAIN_CHAT_RAG:
                    logger.debug(f"DIAGNÓSTICO-RAG: Verificado que el estado {user_key} se actualizó correctamente a STAGE_MAIN_CHAT_RAG en DB")
                else:
                    logger.warning(f"DIAGNÓSTICO-RAG: ¡ALERTA! El estado {user_key} NO se actualizó correctamente a STAGE_MAIN_CHAT_RAG en DB")
    
    except Exception as e:
        logger.error(f"Error al actualizar UserState en DB para {user_key}: {e}", exc_info=True)
        await db_session.rollback()
        # A pesar del error, actualizamos el objeto en memoria para mantener la consistencia del flujo
        if changed_besides_timestamp:
            logger.info(f"UserState {user_key} actualizado SOLO EN MEMORIA con: {updated_fields_log} (falló persistencia en DB)")
    
    if updates.get("stage") == STAGE_SELECTING_BRAND:
        await clear_conversation_history(db_session, user_state_obj.user_id, user_state_obj.platform)

async def reset_user_to_brand_selection(db_session: AsyncSession, user_state_obj: UserState, force: bool = False):
    """
    🔄 ¡Vuelta a empezar! Devuelve al usuario al menú de selección inicial.
    
    Args:
        db_session: Sesión de base de datos activa y lista
        user_state_obj: El perfil de usuario que recibirá un refrescante nuevo comienzo
        force: Un poder especial que mantenemos por compatibilidad, aunque ahora la magia
               del reinicio ocurre siempre, independientemente de dónde se encuentre el usuario
    """
    # CORRECCIÓN: Eliminada la restricción que impedía reiniciar cuando el usuario está en RAG
    # Ahora el comando "Salir" siempre permitirá volver al menú de selección de marca
    
    # Registramos el estado actual antes del reseteo para diagnóstico
    prev_stage = user_state_obj.stage
    prev_brand_id = user_state_obj.current_brand_id
    
    # Para mantener compatibilidad con código existente, mantenemos el log de force
    if force:
        logger.info(f"FORZANDO reseteo de UserState {user_state_obj.platform}:{user_state_obj.user_id} con force=True")

        
    logger.info(f"Reseteando estado del usuario {user_state_obj.platform}:{user_state_obj.user_id} a selección de marca. Force={force}")
        
    fields_to_reset = {
        "current_brand_id": None,
        "stage": STAGE_SELECTING_BRAND,
        "purpose_of_inquiry": None,
        "session_explicitly_ended": False,  # Reiniciar el flag de fin de sesión
        "conversation_history": "[]",  # Explícitamente limpiar el historial de conversación
        # No resetear collected_name, email, phone, o is_subscribed aquí por defecto
    }
    await update_user_state_db(db_session, user_state_obj, fields_to_reset)
    # clear_conversation_history ya se llama dentro de update_user_state_db si stage es STAGE_SELECTING_BRAND
    logger.info(f"UserState {user_state_obj.platform}:{user_state_obj.user_id} reseteado a selección de marca.")
    return

async def update_user_subscription_status(db_session: AsyncSession, user_id: str, platform: str, is_subscribed: bool):
    """Actualiza el estado de suscripción (is_subscribed) de un UserState."""
    # Primero, obtener o crear el usuario para asegurar que exista
    user_state = await get_or_create_user_state(db_session, user_id, platform)
    
    if user_state.is_subscribed != is_subscribed:
        user_state.is_subscribed = is_subscribed
        user_state.last_interaction_at = datetime.now(timezone.utc) # Actualizar timestamp
        db_session.add(user_state) # Marcar para guardar
        logger.info(f"Estado de suscripción para {platform}:{user_id} actualizado a: {is_subscribed} en DB.")
    else:
        logger.info(f"Estado de suscripción para {platform}:{user_id} ya era {is_subscribed}. No cambios en DB.")
    # El commit se hará al final del request en webhook_handler.

async def is_user_subscribed(db_session: AsyncSession, user_id: str, platform: str) -> bool:
    """Verifica si un UserState está suscrito. Si no existe, se considera no suscrito."""
    stmt = select(UserState.is_subscribed).filter_by(user_id=user_id, platform=platform)
    result = await db_session.execute(stmt)
    subscription_status = result.scalar_one_or_none()

    if subscription_status is None:
        logger.debug(f"UserState {platform}:{user_id} no encontrado al verificar suscripción. Considerado NO suscrito.")
        return False
    return subscription_status

# --- Conversation History Management (solución temporal en memoria) ---
_MAX_HISTORY_TURNS = 10  # Guardar N turnos (1 turno = 1 user + 1 assistant)

# Diccionario en memoria para almacenar el historial de conversación temporalmente
# hasta que se implemente la migración para añadir la columna conversation_history
_conversation_history_cache = {}

async def get_conversation_history(db_session: AsyncSession, user_id: str, platform: str) -> List[Dict[str, str]]:
    """Obtiene el historial de conversación para un usuario desde la memoria."""
    user_key = f"{platform}:{user_id}"
    if user_key not in _conversation_history_cache:
        _conversation_history_cache[user_key] = []
    
    return _conversation_history_cache[user_key]

async def add_to_conversation_history(db_session: AsyncSession, user_id: str, platform: str, 
                                       role: str, content: str, include_timestamp: bool = True):
    """
    Añade un mensaje al historial de conversación del usuario con opción de timestamp.
    NOTA: Esta es una implementación temporal en memoria hasta que se implemente 
    la migración para añadir la columna conversation_history a la tabla
    
    Args:
        db_session: Sesión de base de datos activa (no se usa en esta versión temporal)
        user_id: ID único del usuario
        platform: Plataforma (ej: 'whatsapp')
        role: 'user' o 'assistant'
        content: Contenido del mensaje
        include_timestamp: Si se debe incluir timestamp en el mensaje
    """
    user_key = f"{platform}:{user_id}"
    
    # Inicializar el historial si no existe para este usuario
    if user_key not in _conversation_history_cache:
        _conversation_history_cache[user_key] = []
        
    message = {"role": role, "content": content}
    
    if include_timestamp:
        message["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    _conversation_history_cache[user_key].append(message)
    
    # Limitar historial a MAX_HISTORY_TURNS
    max_messages = _MAX_HISTORY_TURNS * 2  # *2 porque cada turno son 2 mensajes
    
    if len(_conversation_history_cache[user_key]) > max_messages:
        _conversation_history_cache[user_key] = _conversation_history_cache[user_key][-max_messages:]
        
    logger.debug(f"Historial actualizado temporalmente para {user_id} en {platform}, mensajes: {len(_conversation_history_cache[user_key])}")
# Código eliminado: referencias a conversation_history

async def clear_conversation_history(db_session: AsyncSession, user_id: str, platform: str):
    """Limpia el historial de conversación para un usuario en la cache en memoria."""
    user_key = f"{platform}:{user_id}"
    
    if user_key in _conversation_history_cache:
        _conversation_history_cache[user_key] = []
        logger.info(f"Historial de conversación limpiado para {user_id} en {platform} (cache en memoria)")
    else:
        logger.debug(f"No hay historial en cache para limpiar para {user_id} en {platform}")


async def remove_last_user_message_from_history(db_session: AsyncSession, user_id: str, platform: str):
    """
    Elimina el último mensaje del usuario del historial de conversación en la cache en memoria.
    
    Útil para evitar registrar mensajes de salida como consultas de RAG.
    
    Args:
        db_session: Sesión de base de datos activa (no usada en esta versión temporal)
        user_id: ID único del usuario
        platform: Plataforma (ej: 'whatsapp')
    """
    user_key = f"{platform}:{user_id}"
    
    if user_key not in _conversation_history_cache or not _conversation_history_cache[user_key]:
        return
    
    # Encontrar el último mensaje del usuario
    history = _conversation_history_cache[user_key]
    for i in range(len(history) - 1, -1, -1):
        if history[i]["role"] == "user":
            logger.info(f"Eliminando último mensaje del usuario del historial (cache): '{history[i]['content']}'")
            history.pop(i)
            _conversation_history_cache[user_key] = history
            break

# --- MENSAJES DE SELECCIÓN ---
async def get_company_selection_message(db_session: AsyncSession, user_state_obj: UserState) -> str:
    """
    ✨ Crea un mensaje de bienvenida interactivo para el usuario con opciones de marcas.
    
    Args:
        db_session: Sesión de base de datos
        user_state_obj: Objeto con el estado actual del usuario
        
    Returns:
        str: Mensaje de bienvenida formateado con opciones interactivas
    """
    logger.info(f"get_company_selection_message para: {user_state_obj.platform}:{user_state_obj.user_id}")
    
    # Obtener nombre del usuario para personalizar el mensaje
    user_name = user_state_obj.collected_name.split()[0] if user_state_obj.collected_name else ""
    
    # Crear el mensaje de bienvenida con formato
    welcome_message = f"¡Un gusto saludarte, {user_name} si me permites el tuteo! 👋 Bienvenido/a al ecosistema de Grupo Beta."
    
    # Cuerpo del mensaje
    body_message = "Soy tu enlace directo con nuestras plataformas de innovación y desarrollo. Mi propósito es ser el catalizador de tus objetivos. 🧠\n\n¿Qué motor de crecimiento te gustaría activar hoy?"
    
    # Obtener las empresas de la base de datos
    companies = await get_all_companies(db_session, force_reload_cache=True)
    
    if not companies:
        return "¡Ups! 😅 Parece que nuestras opciones están tomando un descanso ahora mismo. Por favor, inténtalo de nuevo más tarde."
    
    # Crear opciones de la lista interactiva
    list_items = []
    
    # Mapeo de empresas a sus descripciones
    brand_descriptions = {
        "Javier Bazán": "🎯 Estrategia y Visión de Futuro",
        "Corporativo Ehécatl": "📈 Escalamiento y Optimización Corporativa",
        "Fundación Desarrollemos México": "🌍 Impacto Social y Desarrollo Comunitario",
        "Universidad Digital": "💡 Formación de Talento para la Era Digital",
        "Frente Estudiantil Social": "🌟 Iniciativas y Liderazgo Juvenil"
    }
    
    # Procesar cada empresa
    for idx, company in enumerate(companies[:5], 1):  # Limitar a 5 opciones
        company_name = company.name.strip()
        
        # Normalizar nombre de la empresa para hacer coincidir con las descripciones
        normalized_name = company_name
        if "Javier" in company_name or "Bazán" in company_name:
            normalized_name = "Javier Bazán"
        elif "Ehécatl" in company_name:
            normalized_name = "Corporativo Ehécatl"
        elif "Fundación" in company_name or "Desarrollemos" in company_name:
            normalized_name = "Fundación Desarrollemos México"
        elif "Universidad" in company_name:
            normalized_name = "Universidad Digital"
        elif "Frente Estudiantil" in company_name:
            normalized_name = "Frente Estudiantil Social"
        
        # Obtener descripción o usar el nombre de la empresa si no hay coincidencia
        description = brand_descriptions.get(normalized_name, company_name)
        
        # Extraer emoji y texto de la descripción
        emoji = description[0] if description and description[0] in ["🎯", "📈", "🌍", "💡", "🌟"] else "✨"
        desc_text = description[1:].lstrip() if description and description[0] in ["🎯", "📈", "🌍", "💡", "🌟"] else description
        
        # Crear ítem de lista
        list_item = {
            "id": f"select_brand_{idx}",
            "title": f"{normalized_name}",
            "description": f"{emoji} {desc_text}"
        }
        list_items.append(list_item)
    
    # Crear mensaje final
    footer_message = "*Por favor, selecciona la opción que mejor se alinee con tu meta para continuar.*"
    
    # Construir el mensaje completo
    message = f"{welcome_message}\n\n{body_message}\n\n"
    
    # Agregar opciones numeradas
    for idx, item in enumerate(list_items, 1):
        message += f"{idx}. *{item['title']}*\n   {item['description']}\n\n"
    
    message += f"\n{footer_message}"
    
    # Si hay más de 5 opciones, agregar nota
    if len(companies) > 5:
        message += "\n\n*Nota:* Para ver más opciones, escribe 'más'."
    
    return message

async def get_action_selection_message(company_name: Optional[str], user_state_obj: UserState) -> Dict[str, Any]:
    """
    Crea un mensaje interactivo y personalizado para guiar la siguiente aventura del usuario.
    
    Args:
        company_name: El nombre de la empresa elegida por el usuario
        user_state_obj: Toda la magia y personalidad del usuario
        
    Returns:
        Dict: Una experiencia interactiva con botones y opciones visualmente atractivas
    """
    effective_company_name = company_name if company_name and company_name.strip() else "la entidad seleccionada"
    
    greeting_name_part = ""
    if user_state_obj.collected_name:
        user_first_name = user_state_obj.collected_name.split()[0]
        greeting_name_part = f", {user_first_name}"

    message_text = (f"¡Fantástica elección{greeting_name_part}! ✨ Conectando con *{effective_company_name}*.\n"
                   f"¿Cómo puedo ayudarte a brillar hoy? ✨")

    # Botones de acción rápida
    buttons = [
        {
            "type": "reply",
            "reply": {
                "id": "action_rag",
                "title": "ℹ️ Consultar Información"
            }
        },
        {
            "type": "reply",
            "reply": {
                "id": "action_schedule",
                "title": "📅 Agendar / Ver Horarios"
            }
        }
    ]
    
    # Mantener compatibilidad con el código existente, pero con opciones más atractivas
    text_fallback = f"{message_text}\n\n1. Consultar información sobre {effective_company_name}\n2. Agendar una cita o ver horarios disponibles"
    
    return {
        "text": message_text,
        "buttons": buttons,
        "text_fallback": text_fallback  # Para compatibilidad
    }

# (Opcional) Funciones adicionales que podrías necesitar
async def get_user_state_details(db_session: AsyncSession, user_id: str, platform: str) -> Optional[Dict[str, Any]]:
    stmt = select(UserState).filter_by(user_id=user_id, platform=platform)
    result = await db_session.execute(stmt)
    user = result.scalar_one_or_none()
    if user:
        return {
            "user_id": user.user_id,
            "platform": user.platform,
            "current_brand_id": user.current_brand_id,
            "stage": user.stage,
            "collected_name": user.collected_name,
            "collected_email": user.collected_email,
            "collected_phone": user.collected_phone,
            "purpose_of_inquiry": user.purpose_of_inquiry,
            "is_subscribed": user.is_subscribed,
            "last_interaction_at": user.last_interaction_at,
            "location_info": user.location_info, # Añadido
            "created_at": user.created_at
        }
    return None
