"""
Módulo para integración específica con Azure App Service.
Proporciona utilidades para diagnóstico, logs y gestión del ciclo de vida de la aplicación.
"""
import os
import sys
import logging
import json
import platform
import time
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

# Configurar logger
logger = logging.getLogger(__name__)

class AzureAppServiceHelper:
    """
    Proporciona utilidades específicas para el despliegue y diagnóstico en Azure App Service.
    """
    
    @staticmethod
    def is_running_in_azure() -> bool:
        """Determina si la aplicación está ejecutándose en Azure App Service."""
        return os.environ.get("WEBSITE_SITE_NAME") is not None
    
    @staticmethod
    def get_azure_environment_info() -> Dict[str, Any]:
        """
        Recopila información relevante del entorno de Azure App Service.
        
        Returns:
            Diccionario con información del entorno de Azure.
        """
        if not AzureAppServiceHelper.is_running_in_azure():
            return {"is_azure": False}
            
        env_info = {
            "is_azure": True,
            "site_name": os.environ.get("WEBSITE_SITE_NAME"),
            "instance_id": os.environ.get("WEBSITE_INSTANCE_ID"),
            "resource_group": os.environ.get("WEBSITE_RESOURCE_GROUP"),
            "slot_name": os.environ.get("WEBSITE_SLOT_NAME", "production"),
            "container_name": os.environ.get("CONTAINER_NAME"),
            "website_hostname": os.environ.get("WEBSITE_HOSTNAME"),
            "local_storage_path": os.environ.get("HOME", "/home"),
        }
        
        return env_info
    
    @staticmethod
    def ensure_app_service_directories() -> Dict[str, str]:
        """
        Asegura que los directorios esenciales para Azure App Service existan.
        
        Returns:
            Diccionario con las rutas de los directorios.
        """
        # En Azure App Service, HOME suele ser /home
        base_path = os.environ.get("HOME", "/home")
        
        # Directorios que podrían necesitarse para persistencia
        directories = {
            "data": os.path.join(base_path, "data"),
            "logs": os.path.join(base_path, "LogFiles"),
            "faiss_index": os.path.join(base_path, "data", "faiss_index"),
        }
        
        # Crear directorios si no existen
        for name, path in directories.items():
            try:
                os.makedirs(path, exist_ok=True)
                logger.debug(f"Directorio asegurado: {path}")
            except Exception as e:
                logger.error(f"Error al crear directorio {path}: {e}")
        
        return directories
    
    @staticmethod
    def get_startup_diagnostic_info() -> Dict[str, Any]:
        """
        Recopila información diagnóstica al inicio de la aplicación.
        
        Returns:
            Diccionario con información diagnóstica.
        """
        diag_info = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": platform.platform(),
            "azure_info": AzureAppServiceHelper.get_azure_environment_info(),
            "environment_variables": {
                k: v for k, v in os.environ.items() 
                if not (k.startswith("APPSETTING_") or 
                       "SECRET" in k.upper() or 
                       "PASSWORD" in k.upper() or 
                       "KEY" in k.upper())
            }
        }
        
        # Agregar información sobre montajes de volumen si estamos en Azure
        if AzureAppServiceHelper.is_running_in_azure():
            try:
                # Verificar directorios de persistencia en Azure
                persistent_dirs = AzureAppServiceHelper.ensure_app_service_directories()
                diag_info["persistent_dirs"] = persistent_dirs
                
                # Comprobar permisos en directorios críticos
                permissions_check = {}
                for name, path in persistent_dirs.items():
                    permissions_check[name] = {
                        "exists": os.path.exists(path),
                        "writable": os.access(path, os.W_OK) if os.path.exists(path) else False
                    }
                diag_info["permissions_check"] = permissions_check
            except Exception as e:
                logger.error(f"Error al verificar directorios en Azure: {e}")
                diag_info["directory_check_error"] = str(e)
        
        return diag_info
    
    @staticmethod
    def log_startup_diagnostics() -> None:
        """Registra información diagnóstica de inicio en los logs."""
        try:
            diag_info = AzureAppServiceHelper.get_startup_diagnostic_info()
            
            logger.info("=== DIAGNÓSTICO DE INICIO DE LA APLICACIÓN ===")
            logger.info(f"Timestamp: {diag_info['timestamp']}")
            logger.info(f"Python: {diag_info['python_version']} en {diag_info['platform']}")
            
            # Información de Azure
            if diag_info['azure_info']['is_azure']:
                logger.info(f"Ejecutando en Azure App Service: {diag_info['azure_info'].get('site_name')}")
                logger.info(f"Slot: {diag_info['azure_info'].get('slot_name')}")
                logger.info(f"Hostname: {diag_info['azure_info'].get('website_hostname')}")
                
                if "persistent_dirs" in diag_info:
                    logger.info("--- Directorios persistentes ---")
                    for name, path in diag_info['persistent_dirs'].items():
                        check = diag_info.get('permissions_check', {}).get(name, {})
                        status = "✅" if check.get('exists') and check.get('writable') else "❌"
                        logger.info(f"{status} {name}: {path}")
            else:
                logger.info("Ejecutando en entorno local (no Azure)")
                
            logger.info("===================================")
            
            # Guardar diagnóstico en archivo si estamos en Azure
            if diag_info['azure_info']['is_azure']:
                log_dir = diag_info.get('persistent_dirs', {}).get('logs', '/home/LogFiles')
                os.makedirs(log_dir, exist_ok=True)
                
                log_file = os.path.join(log_dir, "app_startup_diag.json")
                with open(log_file, 'w') as f:
                    json.dump(diag_info, f, indent=2, default=str)
                logger.info(f"Diagnóstico guardado en {log_file}")
        except Exception as e:
            logger.error(f"Error al registrar diagnóstico de inicio: {e}", exc_info=True)
    
    @staticmethod
    def configure_azure_paths_from_env(settings_instance: Any) -> None:
        """
        Configura rutas de archivos específicas para Azure App Service en la configuración.
        
        Args:
            settings_instance: Instancia de configuración de la aplicación.
        """
        if not AzureAppServiceHelper.is_running_in_azure():
            return
            
        try:
            # Obtener ruta base para almacenamiento persistente
            base_path = os.environ.get("HOME", "/home")
            
            # Establecer rutas para directorios persistentes si existen esos atributos
            if hasattr(settings_instance, "DATA_DIR"):
                data_dir = Path(os.path.join(base_path, "data"))
                object.__setattr__(settings_instance, "DATA_DIR", data_dir)
                
            if hasattr(settings_instance, "LOG_DIR"):
                log_dir = Path(os.path.join(base_path, "LogFiles"))
                object.__setattr__(settings_instance, "LOG_DIR", log_dir)
                
            if hasattr(settings_instance, "FAISS_FOLDER_PATH") and hasattr(settings_instance, "FAISS_FOLDER_NAME"):
                # Asegurarse de que data_dir esté definido antes de usarlo
                data_dir = getattr(settings_instance, "DATA_DIR", Path(os.path.join(base_path, "data")))
                faiss_dir = data_dir / settings_instance.FAISS_FOLDER_NAME
                object.__setattr__(settings_instance, "FAISS_FOLDER_PATH", faiss_dir)
                
            # Registrar los cambios
            logger.info("Rutas de directorios configuradas para Azure App Service:")
            for attr in ["DATA_DIR", "LOG_DIR", "FAISS_FOLDER_PATH"]:
                if hasattr(settings_instance, attr):
                    logger.info(f"  {attr}: {getattr(settings_instance, attr)}")
        except Exception as e:
            logger.error(f"Error al configurar rutas para Azure App Service: {e}", exc_info=True)


# Función auxiliar para uso en startup.sh o main.py
def prepare_azure_environment():
    """
    Prepara el entorno para la ejecución en Azure App Service.
    Esta función debe llamarse al inicio de la aplicación.
    """
    if AzureAppServiceHelper.is_running_in_azure():
        AzureAppServiceHelper.ensure_app_service_directories()
        AzureAppServiceHelper.log_startup_diagnostics()
        logger.info("Entorno de Azure App Service preparado correctamente")
    else:
        logger.info("No se detectó Azure App Service, omitiendo preparación específica")
