"""
API de Chat Principal - Integración de RAG, Prompts y LLM

Este módulo proporciona el endpoint principal para el chat que integra:
- Recuperación de documentos relevantes (RAG)
- Prompts personalizados por marca
- Generación de respuestas con LLM
"""

import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from app.utils.logger import logger
from app.ai.rag_retriever import search_relevant_documents
from app.ai.rag_prompt_builder import BRAND_PROFILES, normalize_brand_name_for_search
from app.api.llm_client import generate_chat_completion

# Crear router para chat
chat_router = APIRouter(prefix="/api/chat", tags=["Chat API"])

class ChatRequest(BaseModel):
    """Modelo para solicitudes de chat con soporte para información de usuario y contexto de marca"""
    message: str
    conversation_id: str
    brand_name: Optional[str] = None
    user_info: Optional[Dict[str, Any]] = None

@chat_router.post("")
async def process_chat(request: Request, chat_request: ChatRequest):
    """
    Endpoint principal de chat que integra RAG, prompts personalizados y LLM
    
    El flujo es:
    1. Búsqueda de documentos relevantes con RAG
    2. Selección del perfil de marca adecuado
    3. Construcción del prompt con contexto y perfil
    4. Generación de respuesta con LLM
    """
    # Verificar que el sistema RAG esté disponible
    if not request.app.state.is_rag_ready:
        logger.error("CHAT: Sistema RAG no disponible para consulta")
        raise HTTPException(status_code=503, detail="Servicio de chat no disponible")
    
    logger.info(f"CHAT: Procesando mensaje para conversación: {chat_request.conversation_id}")
    logger.info(f"CHAT: Marca solicitada: {chat_request.brand_name or 'No especificada'}")
    
    try:
        # 1. Buscar documentos relevantes con RAG
        docs = await search_relevant_documents(
            user_query=chat_request.message,
            target_brand=chat_request.brand_name,
            k_final=3
        )
        
        # Registrar cuántos documentos se recuperaron
        doc_count = len(docs) if docs else 0
        logger.info(f"CHAT: Recuperados {doc_count} documentos relevantes")
        
        # 2. Seleccionar perfil de marca
        brand_profile = None
        if chat_request.brand_name:
            # Búsqueda exacta
            if chat_request.brand_name in BRAND_PROFILES:
                brand_profile = BRAND_PROFILES[chat_request.brand_name]
                logger.info(f"CHAT: Usando perfil de marca exacto: {chat_request.brand_name}")
            else:
                # Búsqueda aproximada
                for brand, profile in BRAND_PROFILES.items():
                    if (chat_request.brand_name.lower() in brand.lower() or
                        brand.lower() in chat_request.brand_name.lower()):
                        brand_profile = profile
                        logger.info(f"CHAT: Usando perfil de marca similar: {brand}")
                        break
        
        if not brand_profile and BRAND_PROFILES:
            # Usar primer perfil disponible como fallback
            default_brand = list(BRAND_PROFILES.keys())[0]
            brand_profile = BRAND_PROFILES[default_brand]
            logger.info(f"CHAT: Usando perfil de marca predeterminado: {default_brand}")
        
        # 3. Construir prompt con contexto RAG y perfil de marca
        context_text = ""
        if docs:
            context_text = "\n\n".join([
                f"DOCUMENTO {i+1}:\n{doc.page_content}\n" +
                f"[Fuente: {doc.metadata.get('source', 'No especificada')}]"
                for i, doc in enumerate(docs)
            ])
        
        # Preparar mensajes para el LLM
        system_message = "Eres un asistente útil y profesional."
        if brand_profile:
            # Usar perfil de marca completo
            system_message = f"""
{brand_profile.get('persona_description', 'Eres un asistente útil y profesional.')}

INSTRUCCIONES DE RESPUESTA:
- {brand_profile.get('response_length_guidance', 'Sé conciso y claro.')}
- Tono de comunicación: {', '.join(brand_profile.get('tone_keywords', ['profesional', 'amigable']))}
- {brand_profile.get('conversation_flow_tips', 'Responde directamente a la consulta del usuario.')}

INFORMACIÓN DE CONTACTO:
{brand_profile.get('contact_info_notes', '')}
"""
        
        # Añadir contexto RAG si existe
        if context_text:
            system_message += f"""
CONTEXTO RELEVANTE PARA RESPONDER:
{context_text}

Usa este contexto para responder a la pregunta del usuario. Si la información no está disponible en el contexto, usa el mensaje de fallback apropiado.
"""
        else:
            # Si no hay contexto, usar mensaje de fallback
            system_message += """
No hay información específica disponible en el contexto para esta consulta.
"""
            if brand_profile and brand_profile.get('fallback_no_context'):
                system_message += f"\nUsa este mensaje de fallback: {brand_profile.get('fallback_no_context')}"
        
        # 4. Generar respuesta con LLM
        llm_response = await generate_chat_completion(
            system_message=system_message,
            user_message=chat_request.message
        )
        
        # 5. Construir respuesta
        return {
            "response": llm_response,
            "conversation_id": chat_request.conversation_id,
            "brand_name": chat_request.brand_name,
            "documents_retrieved": doc_count,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"CHAT: Error al procesar consulta: {str(e)}", exc_info=True)
        # Intentar usar mensaje de fallback para errores
        error_response = "Lo siento, ha ocurrido un problema al procesar tu consulta."
        if brand_profile and brand_profile.get('fallback_llm_error'):
            error_response = brand_profile.get('fallback_llm_error')
        
        raise HTTPException(
            status_code=500, 
            detail={
                "error": str(e),
                "fallback_message": error_response
            }
        )
