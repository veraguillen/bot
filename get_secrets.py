#!/usr/bin/env python3
"""
Script temporal para obtener secretos de Azure Key Vault y crear archivo .env local
"""
import os
from app.core.azure_key_vault import key_vault_manager
from app.core.config_enhancer import ConfigEnhancer

def main():
    print("🔐 Obteniendo secretos de Azure Key Vault...")
    
    # Configurar la URL del Key Vault desde variables de entorno
    key_vault_url = os.environ.get("KEY_VAULT_URI")
    if not key_vault_url:
        print("❌ ERROR: KEY_VAULT_URI no está configurado")
        print("Configura la variable de entorno KEY_VAULT_URI con la URL de tu Key Vault")
        return
    
    # Mapeo de secretos según config_enhancer.py
    secret_mappings = {
        "OPENROUTER_API_KEY": "openrouter-api-key",
        "WHATSAPP_ACCESS_TOKEN": "whatsapp-access-token", 
        "WHATSAPP_PHONE_NUMBER_ID": "whatsapp-phone-number-id",
        "WHATSAPP_VERIFY_TOKEN": "whatsapp-verify-token",
        "DATABASE_URL": "database-url",
        "CALENDLY_API_KEY": "calendly-api-key",
        "CALENDLY_EVENT_TYPE_URI": "calendly-event-type-uri",
        "CALENDLY_GENERAL_SCHEDULING_LINK": "calendly-general-scheduling-link"
    }
    
    # Obtener secretos
    secrets = {}
    for env_var, secret_name in secret_mappings.items():
        print(f"📥 Obteniendo {env_var} desde secreto '{secret_name}'...")
        secret_value = key_vault_manager.get_secret(secret_name)
        if secret_value:
            secrets[env_var] = secret_value
            print(f"✅ {env_var} obtenido correctamente")
        else:
            print(f"❌ No se pudo obtener {env_var}")
    
    # Crear archivo .env
    if secrets:
        print("\n📝 Creando archivo .env...")
        with open(".env", "w", encoding="utf-8") as f:
            f.write("# Variables de entorno obtenidas desde Azure Key Vault\n")
            f.write(f"# Key Vault URL: {key_vault_url}\n\n")
            
            for env_var, value in secrets.items():
                f.write(f"{env_var}={value}\n")
            
            # Agregar variables por defecto para desarrollo
            f.write("\n# Variables por defecto para desarrollo local\n")
            f.write("ENVIRONMENT=development\n")
            f.write("LOG_LEVEL=INFO\n")
            f.write("DEBUG=True\n")
            f.write("SERVER_PORT=8000\n")
            f.write("REDIS_URL=redis://localhost:6379/0\n")
            f.write("OPENROUTER_MODEL_CHAT=meta-llama/llama-3-8b-instruct\n")
            f.write("LLM_TEMPERATURE=0.5\n")
            f.write("LLM_MAX_TOKENS=1000\n")
            f.write("LLM_HTTP_TIMEOUT=45.0\n")
        
        print(f"✅ Archivo .env creado con {len(secrets)} variables")
        print("🚀 Ahora puedes ejecutar la aplicación localmente")
    else:
        print("❌ No se pudieron obtener secretos. Verifica:")
        print("1. Que KEY_VAULT_URI esté configurado")
        print("2. Que tengas acceso al Key Vault")
        print("3. Que los nombres de los secretos sean correctos")

if __name__ == "__main__":
    main() 