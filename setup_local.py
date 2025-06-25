#!/usr/bin/env python3
"""
Script para configurar el entorno local paso a paso
"""
import os

def main():
    print("🔧 Configuración del entorno local")
    print("=" * 50)
    
    # Paso 1: Verificar si ya existe .env
    if os.path.exists(".env"):
        print("✅ Archivo .env ya existe")
        choice = input("¿Quieres sobrescribirlo? (s/n): ").lower()
        if choice != 's':
            print("❌ Configuración cancelada")
            return
    
    # Paso 2: Solicitar información del Key Vault
    print("\n📋 Información del Azure Key Vault:")
    print("Necesitas la URL de tu Key Vault. Puedes encontrarla en:")
    print("1. Azure Portal → Key Vaults → Tu Key Vault → Properties → DNS Name")
    print("2. O en GitHub Secrets como KEY_VAULT_URI")
    
    key_vault_url = input("\n🔗 URL del Key Vault (ej: https://mi-keyvault.vault.azure.net/): ").strip()
    
    if not key_vault_url:
        print("❌ URL del Key Vault es requerida")
        return
    
    # Paso 3: Crear archivo .env con configuración básica
    print("\n📝 Creando archivo .env...")
    
    env_content = f"""# Variables de entorno para desarrollo local
# Key Vault URL: {key_vault_url}

# Variables REQUERIDAS (reemplaza con valores reales):
DATABASE_URL=postgresql://user:password@localhost:5432/chatbot_db
OPENROUTER_API_KEY=your_openrouter_api_key_here
WHATSAPP_PHONE_NUMBER_ID=your_whatsapp_phone_number_id
WHATSAPP_ACCESS_TOKEN=your_whatsapp_access_token
WHATSAPP_VERIFY_TOKEN=your_whatsapp_verify_token

# Variables opcionales:
ENVIRONMENT=development
LOG_LEVEL=INFO
DEBUG=True
SERVER_PORT=8000
REDIS_URL=redis://localhost:6379/0
OPENROUTER_MODEL_CHAT=meta-llama/llama-3-8b-instruct
LLM_TEMPERATURE=0.5
LLM_MAX_TOKENS=1000
LLM_HTTP_TIMEOUT=45.0

# Azure Key Vault (para obtener secretos automáticamente):
KEY_VAULT_URI={key_vault_url}
"""
    
    with open(".env", "w", encoding="utf-8") as f:
        f.write(env_content)
    
    print("✅ Archivo .env creado")
    print("\n📋 Próximos pasos:")
    print("1. Reemplaza los valores 'your_*' con las claves reales")
    print("2. O ejecuta: python get_secrets.py (si tienes acceso al Key Vault)")
    print("3. Prueba la aplicación: python main.py")
    
    # Paso 4: Preguntar si quiere probar ahora
    test_now = input("\n¿Quieres probar la aplicación ahora? (s/n): ").lower()
    if test_now == 's':
        print("\n🧪 Probando configuración...")
        try:
            from app.core.config import settings
            print(f"✅ Configuración cargada correctamente")
            print(f"📱 Proyecto: {settings.PROJECT_NAME}")
            print(f"🌍 Entorno: {settings.ENVIRONMENT}")
            print("🚀 La aplicación está lista para ejecutarse")
        except Exception as e:
            print(f"❌ Error al cargar configuración: {e}")
            print("💡 Asegúrate de reemplazar las variables con valores reales")

if __name__ == "__main__":
    main() 