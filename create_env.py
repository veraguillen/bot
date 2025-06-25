#!/usr/bin/env python3
"""
Script para crear el archivo .env con las variables reales de Azure
"""
import os

def create_env_file():
    """Crea el archivo .env con las variables reales"""
    
    env_content = """# Variables de entorno obtenidas desde Azure App Service
# IMPORTANTE: Estas son las variables reales de producción

# Variables REQUERIDAS:
DATABASE_URL=postgresql+asyncpg://useradmin:Chat8121943.@chatbot-iram.postgres.database.azure.com:5432/chatbot_db?ssl=require
OPENROUTER_API_KEY=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
WHATSAPP_PHONE_NUMBER_ID=665300739992317
WHATSAPP_ACCESS_TOKEN=EAAJtmxxtxScBO2rZB0hZAREor30UII4vWncKV3hCOGFlmcIpRmvKNpYROUPW6eHuwbDt7p5JFWHYuZCHcnfbFOHH9TZAMakmnnfdEuoocCzeU63lTsqfSZAD1m05tZBowKMsL6qJLNwHzhtoOpGI5nLf3LWXZBsDo5k985PutKU7vtV2rVb6Wke7dPNmUHkk2XKCQZDZD
WHATSAPP_VERIFY_TOKEN=Julia
VERIFY_TOKEN=Julia

# Variables opcionales:
CALENDLY_API_KEY=eyJraWQiOiIxY2UxZTEzNjE3ZGNmNzY2YjNjZWJjY2Y4ZGM1YmFmYThhNjVlNjg0MDIzZjdjMzJiZTgzNDliMjM4MDEzNWI0IiwidHlwIjoiUEFUIiwiYWxnIjoiRVMyNTYifQ.eyJpc3MiOiJodHRwczovL2F1dGguY2FsZW5kbHkuY29tIiwiaWF0IjoxNzQ2NDc4MDY4LCJqdGkiOiIzZWI0YWJiOS0wNmVjLTQyZGMtYTA5Mi0zMzRkOTY2Y2U5MmIiLCJ1c2VyX3V1aWQiOiIwNzNmNWNkZC0zMTg3LTQzMTgtYTY2Ny1hZTQ2MmFhM2I1YjMifQ.vuP5-9KHIpUXPU4vtROMMjOa--MRj1J5csrkEf9okSw6SvZL3JB1n32H7bQADvuoVAdRn0Xk5nd9IGZBWQz0Xg
CALENDLY_EVENT_TYPE_URI=https://api.calendly.com/event_types/6943da13-c493-4a09-8830-2184f4332a92
CALENDLY_GENERAL_SCHEDULING_LINK=https://calendly.com/chatbotiram-mex/grupobeta
KEY_VAULT_URI=https://AgenteSearchVault.vault.azure.net/
KEY_VAULT_NAME=AgenteSearchVault

# Variables por defecto para desarrollo local:
ENVIRONMENT=development
LOG_LEVEL=INFO
DEBUG=True
SERVER_PORT=8000
REDIS_URL=redis://localhost:6379/0
OPENROUTER_MODEL_CHAT=meta-llama/llama-3-8b-instruct
LLM_TEMPERATURE=0.5
LLM_MAX_TOKENS=1000
LLM_HTTP_TIMEOUT=45.0
"""
    
    # Escribir archivo .env con codificación UTF-8
    with open('.env', 'w', encoding='utf-8') as f:
        f.write(env_content)
    
    print("✅ Archivo .env creado correctamente con codificación UTF-8")
    print("🚀 Ahora puedes ejecutar la aplicación")

if __name__ == "__main__":
    create_env_file() 