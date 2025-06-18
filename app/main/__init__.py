# app/main/__init__.py

# Importar el router desde routes.py
from .routes import router as main_router

# Exportar el router para que pueda ser importado desde otros módulos
__all__ = ["main_router"]