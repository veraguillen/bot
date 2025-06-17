# app/api/calendly.py
import httpx
import json 
from typing import List, Dict, Any, Optional
from app.core.config import settings 
from app.utils.logger import logger
from datetime import datetime, date, timedelta, timezone
import app.utils.validation_utils as local_validators # Para is_valid_email
import locale
import urllib.parse
from fastapi import APIRouter

# --- Configuración de Locale ---
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
    logger.info("Locale configurado a 'es_ES.UTF-8' para formateo de fechas.")
except locale.Error:
    try:
        locale.setlocale(locale.LC_TIME, 'Spanish_Spain.1252')
        logger.info("Locale configurado a 'Spanish_Spain.1252' para formateo de fechas.")
    except locale.Error:
        logger.warning("No se pudo configurar locale a Español. Fechas de Calendly podrían mostrarse en inglés.")

# --- Cliente HTTP para Calendly API ---
_BASE_URL_CALENDLY_API = "https://api.calendly.com"
_HTTP_TIMEOUT_CALENDLY = 20.0 
if settings and hasattr(settings, 'http_client_timeout') and isinstance(settings.http_client_timeout, (int, float)):
    _HTTP_TIMEOUT_CALENDLY = settings.http_client_timeout

# Cliente global para endpoints relativos de Calendly (como /event_type_available_times)
async_client_calendly_relative: Optional[httpx.AsyncClient] = None

def initialize_calendly_clients():
    global async_client_calendly_relative
    if async_client_calendly_relative is None:
        try:
            async_client_calendly_relative = httpx.AsyncClient(
                base_url=_BASE_URL_CALENDLY_API,
                timeout=_HTTP_TIMEOUT_CALENDLY
            )
            logger.info(f"Cliente HTTP para paths relativos de Calendly API inicializado. Base URL: {_BASE_URL_CALENDLY_API}")
        except Exception as e_client:
            logger.error(f"Error al inicializar el cliente HTTP para paths relativos de Calendly: {e_client}", exc_info=True)
            async_client_calendly_relative = None

if settings:
    initialize_calendly_clients()
else:
    logger.error("Settings no disponibles, no se pudo inicializar cliente HTTP de Calendly.")

async def _get_calendly_headers() -> Optional[Dict[str, str]]:
    if not settings or not settings.CALENDLY_API_KEY:
        logger.error("CALENDLY_API_KEY no configurada en settings.")
        return None
    return {'Authorization': f'Bearer {settings.CALENDLY_API_KEY}', 'Content-Type': 'application/json'}

async def get_event_type_details(event_type_absolute_uri: str) -> Optional[Dict[str, Any]]:
    """Obtiene detalles de un tipo de evento usando su URI absoluta."""
    headers = await _get_calendly_headers()
    if not headers: return None
    if not event_type_absolute_uri:
        logger.warning("get_event_type_details: event_type_absolute_uri no proporcionada.")
        return None
        
    logger.debug(f"Obteniendo detalles del tipo de evento desde URL absoluta: {event_type_absolute_uri}")
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_CALENDLY) as temp_client:
            response = await temp_client.get(event_type_absolute_uri, headers=headers)
        response.raise_for_status()
        data = response.json()
        resource_data = data.get("resource")
        if resource_data:
            logger.info(f"Detalles del tipo de evento obtenidos para {event_type_absolute_uri.split('/')[-1]}")
            return resource_data
        else:
            logger.warning(f"Campo 'resource' no encontrado en respuesta para {event_type_absolute_uri}. Respuesta: {data}")
            return None
    except httpx.HTTPStatusError as e_status:
        logger.error(f"Error HTTP {e_status.response.status_code} obteniendo detalles de evento {event_type_absolute_uri}: {e_status.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Error inesperado obteniendo detalles de evento {event_type_absolute_uri}: {e}", exc_info=True)
        return None

async def get_available_slots(
    event_type_uri: str, 
    start_date_obj: Optional[date] = None, 
    end_date_obj: Optional[date] = None
) -> Optional[List[Dict[str, str]]]:
    if async_client_calendly_relative is None:
        logger.error("Cliente HTTP relativo de Calendly no inicializado. No se pueden obtener slots.")
        return None
    headers = await _get_calendly_headers()
    if not headers: return None 
    if not event_type_uri or not event_type_uri.startswith("https://api.calendly.com/event_types/"):
        logger.error(f"URI de tipo de evento inválida o no proporcionada: '{event_type_uri}'")
        return None

    effective_start_date = start_date_obj if start_date_obj is not None else date.today()
    days_to_check = settings.CALENDLY_DAYS_TO_CHECK if settings and hasattr(settings, 'calendly_days_to_check') and isinstance(settings.CALENDLY_DAYS_TO_CHECK, int) else 7
    effective_end_date = end_date_obj if end_date_obj is not None else effective_start_date + timedelta(days=days_to_check)

    start_time_param = datetime.combine(effective_start_date, datetime.min.time()).isoformat(timespec='seconds')
    end_time_param = datetime.combine(effective_end_date, datetime.max.time()).isoformat(timespec='seconds')
    
    invitee_target_timezone = getattr(settings, "CALENDLY_TIMEZONE", "America/Mexico_City") or "America/Mexico_City"

    api_url_path = "/event_type_available_times" 
    params = {
        "event_type": event_type_uri, 
        "start_time": start_time_param,
        "end_time": end_time_param,
        "invitee_timezone": invitee_target_timezone
    }
    logger.info(f"Buscando slots Calendly. Path: {api_url_path}, Params: {params}")
    
    try:
        response = await async_client_calendly_relative.get(api_url_path, headers=headers, params=params)
        if response.status_code == 404:
            logger.error(f"Recurso no encontrado (404) para {event_type_uri} al buscar slots. URL: {response.url}. Respuesta: {response.text[:200]}")
            return None 
        response.raise_for_status() 
        data = response.json()
        available_times_collection = data.get("collection", [])
        if not available_times_collection: logger.info(f"No slots para {event_type_uri}."); return [] 
        slots = []
        for time_info in available_times_collection:
            if time_info.get("status") == "available" and time_info.get("start_time"):
                try:
                    start_time_dt_aware = datetime.fromisoformat(time_info['start_time'].replace('Z', '+00:00'))
                    formatted_time = start_time_dt_aware.strftime(f"%A, %d de %B, %H:%M ({invitee_target_timezone})")
                    slots.append({"start_time_api": time_info['start_time'], "display_time": formatted_time})
                except ValueError: # Fallback para formato de fecha por si strftime falla con locale
                    formatted_time = start_time_dt_aware.strftime(f"%Y-%m-%d %H:%M ({invitee_target_timezone})")
                    slots.append({"start_time_api": time_info['start_time'], "display_time": formatted_time})
                except Exception as parse_err: 
                    logger.warning(f"Error parseando slot: {time_info}. Error: {parse_err}", exc_info=False)
        logger.info(f"Procesados {len(slots)} slots para {event_type_uri.split('/')[-1]}.")
        return slots
    except httpx.HTTPStatusError as e_s: 
        logger.error(f"Error HTTP {e_s.response.status_code} slots Calendly: {e_s.response.text[:200]} (URL: {e_s.request.url})", exc_info=False)
        return None
    except httpx.RequestError as e_r: 
        logger.error(f"Error red slots Calendly: {e_r}", exc_info=True)
        return None
    except Exception as e_g: 
        logger.error(f"Error inesperado slots Calendly: {e_g}", exc_info=True)
        return None

async def get_scheduling_link(
    event_type_uri_from_settings: str, 
    name: Optional[str] = None,
    email: Optional[str] = None
) -> Optional[str]:
    logger.info(f"Obteniendo scheduling link para URI: {event_type_uri_from_settings}")
    
    if not event_type_uri_from_settings:
        logger.error("get_scheduling_link: event_type_uri_from_settings no fue proporcionada.")
        return f"https://calendly.com/{settings.CALENDLY_USER_SLUG if settings and settings.CALENDLY_USER_SLUG else 'tu-usuario'}/#error-no-event-uri"

    event_details = await get_event_type_details(event_type_uri_from_settings)
    
    base_link: Optional[str] = None
    if event_details and event_details.get("scheduling_url"):
        base_link = event_details["scheduling_url"]
    else:
        logger.error(f"No se pudo obtener scheduling_url base para: {event_type_uri_from_settings}")
        user_slug = "tu_usuario_calendly" 
        if settings and hasattr(settings, 'CALENDLY_USER_SLUG') and settings.CALENDLY_USER_SLUG:
            user_slug = settings.CALENDLY_USER_SLUG
        try: event_slug_from_uri = event_type_uri_from_settings.split('/')[-1]; event_slug_from_uri = event_slug_from_uri.split('?')[0]
        except: event_slug_from_uri = "evento-generico"
        logger.warning(f"Usando enlace de fallback. User: {user_slug}, Event Slug (inferido): {event_slug_from_uri}")
        base_link = f"https://calendly.com/{user_slug}/{event_slug_from_uri}"

    logger.debug(f"Enlace base de scheduling: {base_link}")
    
    params_for_link = {}
    if name and name.strip(): params_for_link["name"] = name.strip()
    if email and local_validators.is_valid_email(email): params_for_link["email"] = email.strip()
    
    if settings and getattr(settings, "CALENDLY_TIMEZONE", None):
        params_for_link["timezone"] = settings.CALENDLY_TIMEZONE
        logger.debug(f"Añadiendo timezone='{settings.CALENDLY_TIMEZONE}' al enlace de Calendly.")

    if params_for_link:
        try:
            query_string = urllib.parse.urlencode(params_for_link)
            final_link = f"{base_link}?{query_string}"
            logger.info(f"Enlace de scheduling con parámetros: {final_link}")
            return final_link
        except Exception as e_urlencode:
            logger.error(f"Error codificando params para enlace Calendly: {e_urlencode}")
            return base_link 
    
    logger.info(f"Enlace de scheduling sin parámetros adicionales: {base_link}")
    return base_link

# Configurar el router para los endpoints de Calendly
router = APIRouter()

@router.get("/events", tags=["calendly"])
async def get_events():
    """Obtener eventos de Calendly"""
    return {"message": "Endpoint para obtener eventos de Calendly"}

@router.post("/schedule", tags=["calendly"])
async def schedule_event():
    """Programar un nuevo evento en Calendly"""
    return {"message": "Endpoint para programar eventos en Calendly"}