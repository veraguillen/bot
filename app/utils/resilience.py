"""
Módulo de resiliencia para proteger la aplicación contra fallos en servicios externos.
Implementa circuit breakers para evitar fallos en cascada.
"""
import pybreaker
import logging
import functools
import asyncio
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar('T')
logger = logging.getLogger(__name__)

# Circuit breaker para las llamadas a la API del LLM
llm_breaker = pybreaker.CircuitBreaker(
    fail_max=3,           # Abre el circuito después de 3 fallos consecutivos
    reset_timeout=60,     # Intenta cerrar el circuito después de 60 segundos
    exclude=[KeyboardInterrupt, SystemExit],  # Excepciones que no cuentan como fallos
)

def async_circuit(func: Callable[..., Coroutine[Any, Any, T]]):
    """
    Decorator que aplica un circuit breaker a una función asíncrona.
    Permite detectar fallos consecutivos y evitar llamadas adicionales 
    a un servicio que está fallando.
    """
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            # Adaptamos la función asíncrona a pybreaker que es síncrono
            loop = asyncio.get_running_loop()
            
            # Crear una tarea que se ejecuta en un thread separado
            def run_async_in_sync():
                return llm_breaker.call(
                    lambda: asyncio.run(func(*args, **kwargs))
                )
                
            result = await loop.run_in_executor(None, run_async_in_sync)
            return result
        except pybreaker.CircuitBreakerError as e:
            logger.error(f"Circuit breaker abierto - Servicio no disponible: {e}")
            raise ValueError("Servicio temporalmente no disponible")
    return wrapper
