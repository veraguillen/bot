"""
Módulo para validar la configuración de despliegue y diagnosticar problemas.
Proporciona utilidades para verificar que todos los componentes necesarios estén
correctamente configurados antes del despliegue en Azure.
"""
import os
import sys
import logging
import importlib
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Set, Tuple

# Configurar logger para este módulo
logger = logging.getLogger(__name__)

class DeploymentValidator:
    """Clase para validar la configuración de despliegue y diagnosticar problemas"""

    @staticmethod
    def check_environment() -> Dict[str, Any]:
        """
        Verifica el entorno de ejecución actual y devuelve información relevante.
        
        Returns:
            Diccionario con información del entorno
        """
        env_info = {
            "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
            "platform": sys.platform,
            "in_azure": os.environ.get("WEBSITE_SITE_NAME") is not None,
            "env_variables": {
                "PORT": os.environ.get("PORT"),
                "PYTHONPATH": os.environ.get("PYTHONPATH"),
                "WEBSITE_SITE_NAME": os.environ.get("WEBSITE_SITE_NAME"),
                "DEPLOYMENT_ENV": os.environ.get("DEPLOYMENT_ENV", "development")
            }
        }
        
        logger.info(f"Entorno: Python {env_info['python_version']} en {env_info['platform']}")
        logger.info(f"Ejecutando en Azure: {env_info['in_azure']}")
        
        return env_info
        
    @staticmethod
    def validate_critical_dependencies() -> Dict[str, bool]:
        """
        Verifica que las dependencias críticas estén disponibles.
        
        Returns:
            Diccionario con el estado de las dependencias
        """
        critical_packages = [
            "fastapi", 
            "uvicorn", 
            "pydantic_settings", 
            "langchain", 
            "faiss", 
            "azure.storage.blob", 
            "azure.identity"
        ]
        
        results = {}
        
        for package in critical_packages:
            package_base = package.split('.')[0]  # Para manejar submódulos como azure.storage.blob
            try:
                importlib.import_module(package_base)
                results[package] = True
                logger.info(f"✅ Dependencia {package} disponible")
            except ImportError:
                results[package] = False
                logger.error(f"❌ Dependencia {package} NO disponible")
        
        return results
    
    @staticmethod
    def validate_file_structure() -> Dict[str, Any]:
        """
        Verifica que la estructura de archivos esté completa.
        
        Returns:
            Diccionario con el estado de la estructura de archivos
        """
        required_files = [
            "main.py",
            "Dockerfile",
            "startup.sh",
            "requirements.txt",
            "gunicorn.conf.py",
            "app/main/routes.py",
            "app/core/config.py",
            "app/ai/rag_retriever.py"
        ]
        
        project_root = Path(__file__).resolve().parent.parent.parent
        
        results = {
            "missing_files": [],
            "found_files": []
        }
        
        for file_path in required_files:
            full_path = project_root / file_path
            if full_path.exists():
                results["found_files"].append(file_path)
                logger.debug(f"✅ Archivo {file_path} encontrado")
            else:
                results["missing_files"].append(file_path)
                logger.warning(f"❌ Archivo {file_path} NO encontrado")
        
        results["status"] = len(results["missing_files"]) == 0
        
        if results["status"]:
            logger.info("Estructura de archivos completa")
        else:
            logger.error(f"Faltan archivos en la estructura: {results['missing_files']}")
        
        return results

    @staticmethod
    def check_faiss_index_config() -> Dict[str, Any]:
        """
        Verifica la configuración del índice FAISS.
        
        Returns:
            Diccionario con el estado de la configuración
        """
        try:
            # Importamos aquí para no depender de la estructura global
            from app.core.config import settings
            
            faiss_config = {
                "faiss_index_name": getattr(settings, 'FAISS_INDEX_NAME', None),
                "faiss_folder_name": getattr(settings, 'FAISS_FOLDER_NAME', None),
                "faiss_folder_path": getattr(settings, 'FAISS_FOLDER_PATH', None),
                "storage_account_name": getattr(settings, 'STORAGE_ACCOUNT_NAME', None),
                "container_name": getattr(settings, 'CONTAINER_NAME', None),
                "azure_storage_configured": False,
                "local_index_exists": False
            }
            
            # Verificar si está configurado Azure Storage
            if faiss_config["storage_account_name"] and faiss_config["container_name"]:
                faiss_config["azure_storage_configured"] = True
                logger.info("Azure Storage para FAISS configurado correctamente")
            else:
                logger.warning("Azure Storage para FAISS NO está configurado completamente")
                
            # Verificar si existe el índice local
            if faiss_config["faiss_folder_path"]:
                index_file = Path(faiss_config["faiss_folder_path"]) / f"{faiss_config['faiss_index_name']}.faiss"
                pkl_file = Path(faiss_config["faiss_folder_path"]) / f"{faiss_config['faiss_index_name']}.pkl"
                
                faiss_config["local_index_exists"] = index_file.exists() and pkl_file.exists()
                
                if faiss_config["local_index_exists"]:
                    logger.info(f"Índice FAISS encontrado localmente en {faiss_config['faiss_folder_path']}")
                else:
                    logger.warning(f"Índice FAISS NO encontrado localmente en {faiss_config['faiss_folder_path']}")
            
            return faiss_config
            
        except ImportError as e:
            logger.error(f"No se pudo importar la configuración: {e}")
            return {"error": str(e)}

    @staticmethod
    def generate_deployment_report() -> Dict[str, Any]:
        """
        Genera un informe completo del estado del despliegue.
        
        Returns:
            Diccionario con el informe completo
        """
        validator = DeploymentValidator()
        
        report = {
            "timestamp": import_time.strftime("%Y-%m-%d %H:%M:%S"),
            "environment": validator.check_environment(),
            "dependencies": validator.validate_critical_dependencies(),
            "file_structure": validator.validate_file_structure(),
            "faiss_config": validator.check_faiss_index_config()
        }
        
        # Calcular estado general
        dependencies_ok = all(report["dependencies"].values())
        file_structure_ok = report["file_structure"]["status"]
        faiss_config_ok = "error" not in report["faiss_config"] and (
            report["faiss_config"]["azure_storage_configured"] or 
            report["faiss_config"]["local_index_exists"]
        )
        
        report["status"] = {
            "dependencies": dependencies_ok,
            "file_structure": file_structure_ok,
            "faiss_config": faiss_config_ok,
            "overall": dependencies_ok and file_structure_ok and faiss_config_ok
        }
        
        # Generar recomendaciones
        recommendations = []
        
        if not dependencies_ok:
            missing_deps = [pkg for pkg, status in report["dependencies"].items() if not status]
            recommendations.append(f"Instalar dependencias faltantes: {', '.join(missing_deps)}")
            
        if not file_structure_ok:
            recommendations.append("Corregir la estructura de archivos faltantes")
            
        if not faiss_config_ok:
            if "error" in report["faiss_config"]:
                recommendations.append("Corregir la configuración de FAISS")
            elif not report["faiss_config"]["azure_storage_configured"]:
                recommendations.append("Configurar Azure Storage para FAISS")
            elif not report["faiss_config"]["local_index_exists"]:
                recommendations.append("Asegurar que el índice FAISS esté disponible localmente o en Azure")
                
        report["recommendations"] = recommendations
        
        return report
        
    @staticmethod
    def save_report(report: Dict[str, Any], output_path: Optional[str] = None) -> str:
        """
        Guarda el informe en un archivo JSON.
        
        Args:
            report: Informe generado por generate_deployment_report
            output_path: Ruta donde guardar el archivo. Si es None, se usa un nombre predeterminado.
            
        Returns:
            Ruta donde se guardó el informe
        """
        if output_path is None:
            timestamp = report.get("timestamp", "unknown").replace(" ", "_").replace(":", "-")
            output_path = f"deployment_report_{timestamp}.json"
            
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"Informe guardado en {output_path}")
            return output_path
        except Exception as e:
            logger.error(f"Error al guardar el informe: {e}")
            return ""
            

if __name__ == "__main__":
    # Configurar logging básico si se ejecuta como script
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s'
    )
    
    import time as import_time
    
    # Generar y guardar un informe
    validator = DeploymentValidator()
    report = validator.generate_deployment_report()
    validator.save_report(report)
