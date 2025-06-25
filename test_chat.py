#!/usr/bin/env python3
"""
Script para probar el endpoint de chat
"""
import asyncio
import aiohttp
import json

async def test_chat_endpoint():
    """Prueba el endpoint de chat"""
    
    # URL del endpoint
    url = "http://localhost:8000/api/chat"
    
    # Datos de prueba
    test_data = {
        "message": "Hola, ¿cómo estás?",
        "conversation_id": "test-123",
        "brand_name": "test"
    }
    
    print("🔍 Probando endpoint de chat...")
    print(f"URL: {url}")
    print(f"Datos: {json.dumps(test_data, indent=2)}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=test_data) as response:
                print(f"Status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print("✅ Respuesta exitosa:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Error {response.status}:")
                    print(error_text)
                    return False
                    
    except Exception as e:
        print(f"❌ Error de conexión: {e}")
        return False

async def test_rag_endpoint():
    """Prueba el endpoint de RAG"""
    
    url = "http://localhost:8000/rag/ask"
    
    test_data = {
        "query": "información sobre productos",
        "brand": "test",
        "top_k": 3
    }
    
    print("\n🔍 Probando endpoint de RAG...")
    print(f"URL: {url}")
    print(f"Datos: {json.dumps(test_data, indent=2)}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=test_data) as response:
                print(f"Status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print("✅ Respuesta RAG exitosa:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Error RAG {response.status}:")
                    print(error_text)
                    return False
                    
    except Exception as e:
        print(f"❌ Error de conexión RAG: {e}")
        return False

async def test_rag_status():
    """Prueba el endpoint de estado RAG"""
    
    url = "http://localhost:8000/rag/status"
    
    print("\n🔍 Probando estado de RAG...")
    print(f"URL: {url}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                print(f"Status: {response.status}")
                
                if response.status == 200:
                    result = await response.json()
                    print("✅ Estado RAG:")
                    print(json.dumps(result, indent=2, ensure_ascii=False))
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Error estado RAG {response.status}:")
                    print(error_text)
                    return False
                    
    except Exception as e:
        print(f"❌ Error de conexión estado RAG: {e}")
        return False

async def main():
    """Función principal de prueba"""
    print("🚀 Iniciando pruebas de endpoints...")
    print("=" * 50)
    
    # Probar chat
    chat_ok = await test_chat_endpoint()
    
    print("\n" + "=" * 50)
    
    # Probar estado RAG
    rag_status_ok = await test_rag_status()
    
    print("\n" + "=" * 50)
    
    # Probar RAG
    rag_ok = await test_rag_endpoint()
    
    print("\n" + "=" * 50)
    
    if chat_ok and rag_status_ok and rag_ok:
        print("✅ Todas las pruebas de endpoints pasaron!")
    else:
        print("❌ Algunas pruebas fallaron")
        if not chat_ok:
            print("  - Chat endpoint falló")
        if not rag_status_ok:
            print("  - RAG status endpoint falló")
        if not rag_ok:
            print("  - RAG ask endpoint falló")

if __name__ == "__main__":
    asyncio.run(main()) 