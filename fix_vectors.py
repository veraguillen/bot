#!/usr/bin/env python3
"""
Script para limpiar vectores con dimensiones incorrectas en la base de datos
"""
import asyncio
from sqlalchemy.sql import text
from app.core.database import initialize_database, get_db_engine

async def fix_vector_dimensions():
    """Limpia los vectores con dimensiones incorrectas"""
    
    print("🔧 Solucionando problema de dimensiones de vectores...")
    
    try:
        # Inicializar base de datos
        success = await initialize_database()
        if not success:
            print("❌ No se pudo inicializar la base de datos")
            return False
        
        engine = get_db_engine()
        if not engine:
            print("❌ No se pudo obtener el engine de la base de datos")
            return False
        
        print("✅ Base de datos conectada")
        
        # Limpiar todos los vectores existentes
        async with engine.connect() as conn:
            print("🗑️ Eliminando vectores existentes...")
            
            # Eliminar embeddings
            await conn.execute(text("DELETE FROM langchain_pg_embedding"))
            print("✅ Embeddings eliminados")
            
            # Eliminar colecciones
            await conn.execute(text("DELETE FROM langchain_pg_collection"))
            print("✅ Colecciones eliminadas")
            
            # Commit los cambios
            await conn.commit()
            print("✅ Cambios confirmados")
        
        print("🎉 Base de datos vectorial limpiada correctamente")
        print("📝 Ahora puedes volver a cargar documentos con el modelo de embeddings correcto")
        return True
        
    except Exception as e:
        print(f"❌ Error al limpiar vectores: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Función principal"""
    print("🚀 Iniciando limpieza de vectores...")
    print("=" * 50)
    
    success = await fix_vector_dimensions()
    
    if success:
        print("\n✅ Limpieza completada exitosamente")
        print("💡 Ahora el RAG debería funcionar correctamente")
    else:
        print("\n❌ La limpieza falló")

if __name__ == "__main__":
    asyncio.run(main()) 