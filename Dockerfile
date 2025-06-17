# Dockerfile

# --- Etapa 1: Builder - Construye las dependencias ---
    ARG BUILD_DATE
    ARG VERSION
    
    FROM python:3.10-slim AS builder
    
    # Metadatos de la imagen
    LABEL org.opencontainers.image.created=$BUILD_DATE \
          org.opencontainers.image.version=$VERSION \
          org.opencontainers.image.title="Chatbot Multimarca" \
          org.opencontainers.image.description="Aplicación de chatbot para múltiples marcas" \
          org.opencontainers.image.vendor="Tu Empresa"
    
    # Variables de entorno para un build limpio y eficiente
    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PIP_NO_CACHE_DIR=1 \
        PIP_DISABLE_PIP_VERSION_CHECK=1 \
        PIP_DEFAULT_TIMEOUT=100
    
    WORKDIR /app
    
    # Instala dependencias del sistema para compilar paquetes de Python
    RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        python3-dev \
        libpq-dev \
        # Limpia la caché de apt en la misma capa para reducir el tamaño
        && rm -rf /var/lib/apt/lists/*
    
    # Copia e instala dependencias de Python
    COPY requirements.txt .
    RUN pip install --upgrade pip && \
        pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt
    
    
    # --- Etapa 2: Runtime - Imagen final y segura ---
    FROM python:3.10-slim
    
    # Variables de entorno para la caché y la aplicación
    ENV PYTHONDONTWRITEBYTECODE=1 \
        PYTHONUNBUFFERED=1 \
        PYTHONPATH=/app \
        PATH="/home/appuser/.local/bin:$PATH" \
        PYTHONFAULTHANDLER=1 \
        PYTHONHASHSEED=random \
        PIP_NO_CACHE_DIR=1 \
        HF_HOME=/app/cache \
        TRANSFORMERS_CACHE=/app/cache \
        TORCH_HOME=/app/cache
    
    # Crear usuario no root y los directorios necesarios con los permisos correctos
    RUN groupadd -r appuser --gid 1001 && \
        useradd -r -g appuser --uid 1001 -d /home/appuser -m appuser && \
        # Se crean los directorios /app y /app/cache, y se asigna la propiedad a 'appuser'
        mkdir -p /app/cache && \
        chown -R appuser:appuser /app /home/appuser
    
    WORKDIR /app
    
    # Instala dependencias del sistema mínimas para el runtime
    RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
        netcat-traditional \
        # Limpia la caché para reducir el tamaño de la imagen final
        && rm -rf /var/lib/apt/lists/*
    
    # Copia las dependencias pre-compiladas desde la etapa de construcción
    COPY --from=builder --chown=appuser:appuser /wheels /wheels
    COPY --from=builder --chown=appuser:appuser /app/requirements.txt .
    
    # Instala dependencias de Python desde los wheels locales y luego limpia
    RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt && \
        rm -rf /wheels
    
    # Copia la aplicación completa
    COPY --chown=appuser:appuser . .
    
    # Dale permisos de ejecución a tu script de inicio
    RUN chmod +x ./startup.sh
    
    # Cambia al usuario no root
    USER appuser
    
    # Puerto expuesto
    EXPOSE 8000
    
    # Healthcheck
    # --- CORRECCIÓN FINAL: Apuntando a la ruta exacta /api/health/ ---
    # Se aumenta el start_period para darle tiempo a la app de descargar modelos.
    HEALTHCHECK --interval=30s --timeout=15s --start-period=60s --retries=3 \
        CMD curl -f http://localhost:8000/api/health/ || exit 1
    
    # Comando de inicio
    # Usa el script robusto como única fuente de verdad para el arranque.
    CMD ["./startup.sh"]