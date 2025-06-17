#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Interfaz Chainlit para el Chatbot Multimarca Beta - Versión Simplificada.
"""

import os
import sys
import chainlit as cl
from typing import Dict, List, Optional

# Deshabilitar BD de Chainlit para evitar errores de conexión
os.environ["CHAINLIT_DATABASE_URL"] = ""

# Asegurar que el directorio raíz está en el path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Importaciones necesarias de la aplicación
from app.core.database import get_db_session, initialize_database
from app.main.state_manager import (
    get_or_create_user_state,
    get_company_selection_message,
    add_to_conversation_history,
    get_company_id_by_selection, 
    update_user_state_db,
    reset_user_to_brand_selection
)
from app.api.llm_client import create_llm_client
import logging

# Configurar logger para depuración
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("chainlit_app")

# Variables globales para manejar sesión sin datos
user_id_global = "web_user_chainlit"
platform_global = "web"

@cl.on_chat_start
async def start():
    """Inicializa el chat y muestra mensaje de bienvenida"""
    # Inicializar y verificar la base de datos
    await cl.Message(content="Iniciando Chatbot Multimarca...").send()
    
    db_initialized = await initialize_database()
    if not db_initialized:
        await cl.Message(content="⚠️ Error: No se pudo conectar a la base de datos.").send()
        return
    
    # Crear botón de reinicio
    actions = [
        cl.Action(name="reset", value="reset", label="🔄 Reiniciar Conversación", payload={})
    ]
    
    # Mensaje de bienvenida con selección de marca
    async for db in get_db_session():
        try:
            user_state = await get_or_create_user_state(db, user_id_global, platform_global)
            welcome_message = await get_company_selection_message(db, user_state)
            await cl.Message(content=welcome_message, actions=actions).send()
        except Exception as e:
            logger.error(f"Error al iniciar chat: {str(e)}")
            await cl.Message(content=f"Error al iniciar: {str(e)}").send()

@cl.on_message
async def on_message(message: cl.Message):
    """Procesa mensajes del usuario"""
    async for db in get_db_session():
        try:
            # Indicador de procesamiento
            processing_msg = await cl.Message(content="✨ Procesando...").send()
            
            # Obtener estado actual del usuario
            user_state = await get_or_create_user_state(db, user_id_global, platform_global)
            
            # Registrar mensaje del usuario
            await add_to_conversation_history(db, user_id_global, platform_global, "user", message.content)
            
            # Procesamiento de respuesta según etapa
            if user_state.current_stage == "selecting_brand":
                # Selección de empresa
                try:
                    # Mostrar información de depuración
                    print(f"Intentando procesar selección: '{message.content}'")
                    
                    # Si es un número, intentar convertirlo
                    selection = message.content.strip()
                    if selection.isdigit():
                        print(f"Detectada selección numérica: {selection}")
                    
                    # Obtener ID de empresa
                    company_id = await get_company_id_by_selection(db, selection)
                    print(f"Resultado de get_company_id_by_selection: {company_id}")
                    
                    if company_id:
                        print(f"Actualizando estado con company_id={company_id}")
                        # Actualizar estado
                        await update_user_state_db(db, user_state, {
                            "selected_company_id": company_id,
                            "current_stage": "main_chat_rag"
                        })
                        response = "Has seleccionado la empresa correctamente. ¿En qué puedo ayudarte?"
                    else:
                        response = "No reconozco esa empresa. Por favor, selecciona una opción válida."
                except Exception as e:
                    logger.error(f"Error al procesar selección de empresa: {str(e)}")
                    response = f"Error al procesar tu selección. Por favor, intenta de nuevo."
            else:
                # Modo chatbot normal
                try:
                    # Verificar que existe una empresa seleccionada
                    if not user_state.selected_company_id:
                        print("Error: No hay empresa seleccionada")
                        response = "Por favor, selecciona una empresa primero."
                        # Reiniciar a selección de empresa
                        await reset_user_to_brand_selection(db, user_state)
                    else:  
                        # Crear cliente LLM
                        llm_client = create_llm_client()
                        print(f"Empresa seleccionada ID: {user_state.selected_company_id}")
                        # Respuesta simple para prueba
                        response = f"Recibí tu mensaje sobre la empresa ID {user_state.selected_company_id}:\n\n{message.content}\n\nEsta es una respuesta de prueba. La integración RAG completa está pendiente."
                except Exception as e:
                    logger.error(f"Error en modo chatbot: {str(e)}")
                    response = f"Error al procesar tu mensaje: {str(e)}"
            
            # Registrar respuesta
            await add_to_conversation_history(db, user_id_global, platform_global, "assistant", response)
            
            # Eliminar mensaje de procesamiento y enviar respuesta
            await processing_msg.remove()
            
            # Botón de reinicio
            actions = [
                cl.Action(name="reset", value="reset", label="🔄 Reiniciar", payload={})
            ]
            await cl.Message(content=response, actions=actions).send()
            
        except Exception as e:
            logger.error(f"Error al procesar mensaje: {str(e)}")
            await cl.Message(content=f"Error: {str(e)}").send()

@cl.action_callback("reset")
async def on_reset(action):
    """Reinicia la conversación"""
    await cl.Message(content="Reiniciando conversación...").send()
    
    async for db in get_db_session():
        try:
            # Reiniciar estado
            user_state = await get_or_create_user_state(db, user_id_global, platform_global)
            await reset_user_to_brand_selection(db, user_state)
            
            # Obtener nuevo mensaje de bienvenida
            welcome_message = await get_company_selection_message(db, user_state)
            
            # Enviar mensaje con botón de reinicio
            actions = [
                cl.Action(name="reset", value="reset", label="🔄 Reiniciar", payload={})
            ]
            await cl.Message(content=welcome_message, actions=actions).send()
        except Exception as e:
            logger.error(f"Error al reiniciar: {str(e)}")
            await cl.Message(content=f"Error al reiniciar: {str(e)}").send()
