"""
Módulo para manejar la integración con Azure Key Vault y obtener secretos
de forma segura en el entorno de Azure.
"""
import os
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

try:
    from azure.identity import DefaultAzureCredential, ManagedIdentityCredential
    from azure.keyvault.secrets import SecretClient
    AZURE_KV_AVAILABLE = True
except ImportError:
    logger.warning("Azure Key Vault SDK no disponible. La gestión de secretos con Azure Key Vault no funcionará.")
    AZURE_KV_AVAILABLE = False

class AzureKeyVaultManager:
    """Gestiona la obtención de secretos desde Azure Key Vault."""
    
    def __init__(self, vault_url: Optional[str] = None):
        """
        Inicializa el gestor de Azure Key Vault.
        
        Args:
            vault_url: URL del Azure Key Vault. Si es None, se intentará obtener de
                      la variable de entorno AZURE_KEY_VAULT_URL.
        """
        self._vault_url = vault_url or os.environ.get("AZURE_KEY_VAULT_URL")
        self._client = None
        self._secrets_cache: Dict[str, str] = {}
        
        # Determinar si estamos en un entorno de Azure
        self._in_azure = os.environ.get("WEBSITE_SITE_NAME") is not None
        
        if not AZURE_KV_AVAILABLE:
            logger.error("Azure Key Vault SDK no instalado. Instala 'azure-keyvault-secrets' y 'azure-identity'.")
            return
            
        if not self._vault_url:
            logger.warning("URL de Azure Key Vault no provista. La integración con Key Vault está deshabilitada.")
            return
            
        try:
            if self._in_azure:
                # En Azure, usar Managed Identity
                credential = ManagedIdentityCredential()
                logger.info(f"Inicializando Azure Key Vault con Managed Identity en {self._vault_url}")
            else:
                # Desarrollo local, usar DefaultAzureCredential
                credential = DefaultAzureCredential()
                logger.info(f"Inicializando Azure Key Vault con DefaultAzureCredential en {self._vault_url}")
            
            self._client = SecretClient(vault_url=self._vault_url, credential=credential)
            logger.info("Cliente de Azure Key Vault inicializado correctamente.")
        except Exception as e:
            logger.error(f"Error inicializando Azure Key Vault: {str(e)}")
            self._client = None
    
    @property
    def is_available(self) -> bool:
        """Devuelve True si Azure Key Vault está disponible y configurado."""
        return AZURE_KV_AVAILABLE and self._client is not None
    
    def get_secret(self, secret_name: str, use_cache: bool = True) -> Optional[str]:
        """
        Obtiene un secreto de Azure Key Vault.
        
        Args:
            secret_name: Nombre del secreto a obtener.
            use_cache: Si es True, se usará la caché local si el secreto ya ha sido consultado.
            
        Returns:
            El valor del secreto o None si no se puede obtener.
        """
        if not self.is_available:
            logger.warning(f"Azure Key Vault no disponible. No se puede obtener el secreto '{secret_name}'.")
            return None
        
        # Usar caché si está habilitada y el secreto ya está en caché
        if use_cache and secret_name in self._secrets_cache:
            return self._secrets_cache[secret_name]
        
        try:
            secret = self._client.get_secret(secret_name)
            if secret and secret.value:
                # Guardar en caché para futuras llamadas
                if use_cache:
                    self._secrets_cache[secret_name] = secret.value
                return secret.value
            return None
        except Exception as e:
            logger.error(f"Error obteniendo secreto '{secret_name}' de Azure Key Vault: {str(e)}")
            return None
            
    def get_secrets_dict(self, secret_names: list[str]) -> Dict[str, Optional[str]]:
        """
        Obtiene múltiples secretos de Azure Key Vault y los devuelve en un diccionario.
        
        Args:
            secret_names: Lista de nombres de secretos a obtener.
            
        Returns:
            Diccionario con los nombres de secretos como claves y sus valores como valores.
        """
        result = {}
        for name in secret_names:
            result[name] = self.get_secret(name)
        return result

# Instancia global para usar en toda la aplicación
key_vault_manager = AzureKeyVaultManager()
