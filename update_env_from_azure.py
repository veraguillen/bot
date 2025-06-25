#!/usr/bin/env python3
"""
Script para actualizar el archivo .env local con variables reales de Azure
"""
import subprocess
import json
import os

def get_azure_app_settings():
    """Obtiene las variables de entorno desde Azure App Service"""
    try:
        result = subprocess.run([
            'az', 'webapp', 'config', 'appsettings', 'list',
            '--name', 'chat-app-4313',
            '--resource-group', 'beta-bot',
            '--output', 'json'
        ], capture_output=True, text=True, check=True)
        
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        print(f"❌ Error al obtener configuraciones de Azure: {e}")
        return None

def update_env_file(settings):
    """Actualiza el archivo .env con las variables de Azure"""
    
    # Variables importantes para desarrollo local
    important_vars = {
        'DATABASE_URL': 'DATABASE_URL',
        'OPENROUTER_API_KEY': 'OPENROUTER_API_KEY',
        'WHATSAPP_PHONE_NUMBER_ID': 'WHATSAPP_PHONE_NUMBER_ID',
        'WHATSAPP_ACCESS_TOKEN': 'WHATSAPP_ACCESS_TOKEN',
        'WHATSAPP_VERIFY_TOKEN': 'WHATSAPP_VERIFY_TOKEN',
        'VERIFY_TOKEN': 'VERIFY_TOKEN',
        'CALENDLY_API_KEY': 'CALENDLY_API_KEY',
        'CALENDLY_EVENT_TYPE_URI': 'CALENDLY_EVENT_TYPE_URI',
        'CALENDLY_GENERAL_SCHEDULING_LINK': 'CALENDLY_GENERAL_SCHEDULING_LINK',
        'KEY_VAULT_URI': 'KEY_VAULT_URI',
        'KEY_VAULT_NAME': 'KEY_VAULT_NAME'
    }
    
    # Crear contenido del archivo .env
    env_content = "# Variables de entorno obtenidas desde Azure App Service\n"
    env_content += "# IMPORTANTE: Estas son las variables reales de producción\n\n"
    
    # Agregar variables importantes
    for azure_name, env_name in important_vars.items():
        for setting in settings:
            if setting['name'] == azure_name:
                env_content += f"{env_name}={setting['value']}\n"
                break
    
    # Agregar variables por defecto para desarrollo local
    env_content += "\n# Variables por defecto para desarrollo local\n"
    env_content += "ENVIRONMENT=development\n"
    env_content += "LOG_LEVEL=INFO\n"
    env_content += "DEBUG=True\n"
    env_content += "SERVER_PORT=8000\n"
    env_content += "REDIS_URL=redis://localhost:6379/0\n"
    env_content += "OPENROUTER_MODEL_CHAT=meta-llama/llama-3-8b-instruct\n"
    env_content += "LLM_TEMPERATURE=0.5\n"
    env_content += "LLM_MAX_TOKENS=1000\n"
    env_content += "LLM_HTTP_TIMEOUT=45.0\n"
    
    # Escribir archivo .env
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print("✅ Archivo .env actualizado con variables reales de Azure")
    print("🚀 Ahora puedes ejecutar la aplicación localmente")

def main():
    print("🔐 Obteniendo variables de entorno desde Azure...")
    
    # Obtener configuraciones de Azure
    settings = get_azure_app_settings()
    
    if not settings:
        print("❌ No se pudieron obtener las configuraciones de Azure")
        return
    
    print(f"✅ Se obtuvieron {len(settings)} configuraciones de Azure")
    
    # Actualizar archivo .env
    update_env_file(settings)
    
    print("\n📋 Variables importantes obtenidas:")
    important_vars = ['DATABASE_URL', 'OPENROUTER_API_KEY', 'WHATSAPP_PHONE_NUMBER_ID', 
                     'WHATSAPP_ACCESS_TOKEN', 'WHATSAPP_VERIFY_TOKEN', 'VERIFY_TOKEN']
    
    for var_name in important_vars:
        for setting in settings:
            if setting['name'] == var_name:
                value = setting['value']
                # Mostrar solo los primeros y últimos caracteres por seguridad
                if len(value) > 10:
                    display_value = f"{value[:10]}...{value[-10:]}"
                else:
                    display_value = "***"
                print(f"  {var_name}: {display_value}")
                break

if __name__ == "__main__":
    main() 