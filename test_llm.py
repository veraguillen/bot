#!/usr/bin/env python3
"""
Script para probar específicamente el LLM
"""
import asyncio
import json
from app.api.llm_client import generate_chat_completion, _get_validated_base_url
from app.core.config import settings

async def test_llm():
    """Prueba el LLM directamente"""
    
    print("🔍 Probando LLM directamente...")
    
    try:
        # Verificar configuración
        base_url = _get_validated_base_url()
        print(f"🔧 URL base: {base_url}")
        print(f"🔧 Modelo: {settings.OPENROUTER_MODEL_CHAT}")
        print(f"🔧 API Key configurada: {bool(settings.OPENROUTER_API_KEY)}")
        
        # Probar con un mensaje simple
        system_message = "Eres un asistente útil y profesional."
        user_message = "Hola, ¿cómo estás?"
        
        print(f"System: {system_message}")
        print(f"User: {user_message}")
        
        # Verificar que el modelo se está leyendo correctamente
        print(f"🔧 Modelo que se enviará: {settings.OPENROUTER_MODEL_CHAT}")
        
        response = await generate_chat_completion(
            system_message=system_message,
            user_message=user_message
        )
        
        print(f"✅ Respuesta LLM: {response}")
        return True
        
    except Exception as e:
        print(f"❌ Error en LLM: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Función principal"""
    print("🚀 Probando LLM...")
    print("=" * 50)
    
    success = await test_llm()
    
    if success:
        print("✅ LLM funciona correctamente")
    else:
        print("❌ LLM tiene problemas")

if __name__ == "__main__":
    asyncio.run(main()) 