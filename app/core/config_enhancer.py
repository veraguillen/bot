"""
Módulo para mejorar la configuración con integración de Azure Key Vault.
Permite cargar secretos desde Azure Key Vault y actualizar la configuración de la aplicación.
"""
import logging
import os
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

from app.core.azure_key_vault import key_vault_manager

logger = logging.getLogger(__name__)

class ConfigEnhancer:
    """
    Clase para mejorar la configuración de la aplicación con valores
    provenientes de Azure Key Vault u otros proveedores de configuración.
    """
    
    @staticmethod
    def update_settings_from_key_vault(settings_instance: Any, secret_mappings: Dict[str, str]) -> None:
        """
        Actualiza la configuración de la aplicación con valores de Azure Key Vault.
        
        Args:
            settings_instance: Instancia de configuración (Settings) a actualizar
            secret_mappings: Diccionario que mapea nombres de atributos de settings a nombres de secretos en Key Vault
                             Por ejemplo: {"OPENROUTER_API_KEY": "openrouter-api-key"}
        """
        if not key_vault_manager.is_available:
            logger.warning("Azure Key Vault no está disponible. No se actualizarán las configuraciones desde secretos.")
            return
        
        logger.info("Actualizando configuración desde Azure Key Vault...")
        
        for attr_name, secret_name in secret_mappings.items():
            # Obtener el secreto de Key Vault
            secret_value = key_vault_manager.get_secret(secret_name)
            
            if secret_value is not None:
                try:
                    # Actualizar la configuración solo si el secreto se obtuvo correctamente
                    setattr(settings_instance, attr_name, secret_value)
                    # Log seguro (no muestra el valor del secreto)
                    logger.info(f"Configuración '{attr_name}' actualizada desde secreto '{secret_name}'")
                except Exception as e:
                    logger.error(f"Error al establecer configuración '{attr_name}' desde secreto '{secret_name}': {str(e)}")
            else:
                logger.warning(f"No se pudo obtener el secreto '{secret_name}' para configuración '{attr_name}'")
    
    @staticmethod
    def get_secret_mappings_for_mlops() -> Dict[str, str]:
        """
        Devuelve un diccionario con mappings de atributos de configuración a nombres de secretos en Key Vault
        para las configuraciones relacionadas con MLOps.
        """
        return {
            # Credenciales de Azure Storage
            "AZURE_STORAGE_CONNECTION_STRING": "azure-storage-connection-string",
            "STORAGE_ACCOUNT_NAME": "azure-storage-account-name",
            "CONTAINER_NAME": "azure-storage-container-name",
            
            # Credenciales de Base de Datos
            "PGUSER": "postgres-user",
            "PGPASSWORD": "postgres-password",
            "PGHOST": "postgres-host",
            "PGDATABASE": "postgres-database",
            
            # Credenciales de APIs
            "OPENROUTER_API_KEY": "openrouter-api-key",
            "WHATSAPP_ACCESS_TOKEN": "whatsapp-access-token",
            "CALENDLY_API_KEY": "calendly-api-key",
        }
    
    @staticmethod
    def check_missing_critical_configs(settings_instance: Any, critical_configs: List[str]) -> List[str]:
        """
        Verifica si hay configuraciones críticas faltantes.
        
        Args:
            settings_instance: Instancia de configuración a verificar
            critical_configs: Lista de nombres de atributos críticos que deben estar configurados
            
        Returns:
            Lista de nombres de configuraciones críticas faltantes
        """
        missing = []
        
        for config_name in critical_configs:
            # Verificar si el atributo existe y no es None o string vacío
            if not hasattr(settings_instance, config_name):
                missing.append(config_name)
            else:
                value = getattr(settings_instance, config_name)
                if value is None or (isinstance(value, str) and not value.strip()):
                    missing.append(config_name)
                    
        return missing
