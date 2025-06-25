#!/usr/bin/env python3
"""
Script para probar la conexión a la base de datos
"""
import asyncio
import os
from pathlib import Path

# Cargar variables de entorno
from dotenv import load_dotenv
PROJECT_ROOT = Path(__file__).resolve().parent
dotenv_path = PROJECT_ROOT / ".env"
if dotenv_path.exists():
    load_dotenv(dotenv_path=dotenv_path)
    print(f"✅ Variables de entorno cargadas desde {dotenv_path}")

async def test_database_connection():
    """Prueba la conexión a la base de datos"""
    try:
        from app.core.database import initialize_database, get_db_engine
        
        print("🔍 Probando inicialización de la base de datos...")
        
        # Intentar inicializar la base de datos
        success = await initialize_database()
        
        if success:
            print("✅ Base de datos inicializada correctamente")
            
            # Obtener el engine
            engine = get_db_engine()
            if engine:
                print("✅ Engine de base de datos disponible")
                
                # Probar una consulta simple
                from sqlalchemy.sql import text
                async with engine.connect() as conn:
                    result = await conn.execute(text("SELECT 1 as test"))
                    row = result.fetchone()
                    print(f"✅ Consulta de prueba exitosa: {row}")
                    
                return True
            else:
                print("❌ Engine de base de datos no disponible")
                return False
        else:
            print("❌ Fallo en la inicialización de la base de datos")
            return False
            
    except Exception as e:
        print(f"❌ Error al probar la base de datos: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_config():
    """Prueba la configuración"""
    try:
        from app.core.config import settings
        
        print("🔍 Probando configuración...")
        print(f"✅ PROJECT_NAME: {settings.PROJECT_NAME}")
        print(f"✅ ENVIRONMENT: {settings.ENVIRONMENT}")
        print(f"✅ DATABASE_URL: {str(settings.DATABASE_URL)[:50]}...")
        print(f"✅ OPENROUTER_API_KEY: {settings.OPENROUTER_API_KEY[:20]}...")
        print(f"✅ WHATSAPP_PHONE_NUMBER_ID: {settings.WHATSAPP_PHONE_NUMBER_ID}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error al probar la configuración: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Función principal de prueba"""
    print("🚀 Iniciando pruebas del sistema...")
    print("=" * 50)
    
    # Probar configuración
    config_ok = await test_config()
    if not config_ok:
        print("❌ Fallo en la configuración")
        return
    
    print("\n" + "=" * 50)
    
    # Probar base de datos
    db_ok = await test_database_connection()
    if not db_ok:
        print("❌ Fallo en la base de datos")
        return
    
    print("\n" + "=" * 50)
    print("✅ Todas las pruebas pasaron correctamente!")
    print("🚀 El sistema está listo para funcionar")

if __name__ == "__main__":
    asyncio.run(main()) 