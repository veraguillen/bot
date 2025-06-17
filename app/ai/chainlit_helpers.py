#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Helpers para la integración con Chainlit.
"""

import asyncio
from typing import Dict, List, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.logger import logger
from app.ai.rag_retriever import search_relevant_documents
from app.ai.rag_prompt_builder import build_rag_prompt
from app.models import Company
from app.main.state_manager import get_company_by_id

async def process_rag_query(
    db_session: AsyncSession,
    query: str,
    llm_client: Any,
    conversation_history: List[Dict[str, str]],
    company_id: Optional[int] = None
) -> str:
    """
    Procesa una consulta RAG utilizando la infraestructura existente.
    
    Args:
        db_session: Sesión de base de datos activa
        query: Consulta del usuario
        llm_client: Cliente LLM inicializado
        conversation_history: Historial de la conversación
        company_id: ID de la compañía seleccionada (opcional)
        
    Returns:
        str: Respuesta generada
    """
    try:
        # Obtener información de la empresa si se proporciona company_id
        company_name = None
        if company_id:
            company = await get_company_by_id(db_session, company_id)
            if company:
                company_name = company.nombre
        
        # Buscar documentos relevantes
        logger.info(f"Procesando consulta RAG: '{query}' para empresa: '{company_name}'")
        relevant_docs = await search_relevant_documents(
            user_query=query,
            target_brand=company_name
        )
        
        if not relevant_docs:
            return "Lo siento, no encontré información específica sobre tu consulta en nuestra base de conocimiento. ¿Podrías reformular tu pregunta o consultar sobre otro tema?"
        
        # Extraer el contenido de los documentos para el contexto
        context = [doc.page_content for doc in relevant_docs] if relevant_docs else []
        
        # Construir el prompt RAG
        prompt = await build_rag_prompt(
            query=query,
            context=context,
            brand_name=company_name,
            conversation_history=conversation_history
        )
        
        # Generar respuesta con el LLM
        response = await llm_client.generate_response(prompt=prompt)
        return response
        
    except Exception as e:
        logger.error(f"Error al procesar consulta RAG: {str(e)}")
        return f"Lo siento, ha ocurrido un error al procesar tu consulta. Por favor, inténtalo de nuevo más tarde. Error: {str(e)}"
