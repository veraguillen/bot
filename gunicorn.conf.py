import os
import multiprocessing

# Configuración de Gunicorn

# --- Optimización de Rendimiento y Memoria ---
# Carga la aplicación antes de crear los workers.
# Esencial para aplicaciones con modelos de ML pesados para evitar
# cargar el modelo en memoria por cada worker.
preload_app = True

# --- Configuración de Workers y Threads ---
# Puedes controlar esto desde las variables de entorno o fijarlo aquí.
workers = int(os.getenv("WORKERS", "2"))
threads = int(os.getenv("THREADS", "4"))  # Buena práctica para workers uvicorn

# --- Binding ---
# El bind se manejará desde el startup.sh para mayor flexibilidad.
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"

# --- Timeouts ---
timeout = int(os.getenv("TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GRACEFUL_TIMEOUT", "30"))
keepalive = 5

# --- Logging ---
# Los logs se redirigen a stdout/stderr, que es lo ideal para contenedores Docker
worker_class = "uvicorn.workers.UvicornWorker"
errorlog = "-"
accesslog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'
loglevel = os.getenv("LOG_LEVEL", "info")