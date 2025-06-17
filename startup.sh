#!/bin/bash
# Aumenta la robustez del script deteniéndose ante cualquier error.
set -e

# --- Configuración ---
APP_PORT=${SERVER_PORT:-8000}
WORKERS=${WORKERS:-2}
TIMEOUT=${TIMEOUT:-120}
LOG_LEVEL=${LOG_LEVEL:-info}
HOST="0.0.0.0"

# --- Funciones ---
log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] [STARTUP] $1"
}

check_env_vars() {
    log "Verificando variables de entorno requeridas..."
    local required_vars=(
        "DATABASE_URL"
        "WHATSAPP_ACCESS_TOKEN"
        "WHATSAPP_PHONE_NUMBER_ID"
    )
    for var in "${required_vars[@]}"; do
        if [ -z "${!var}" ]; then
            log "❌ ERROR: La variable de entorno '$var' no está configurada. Abortando."
            exit 1
        fi
    done
    log "✅ Verificación de variables de entorno completada."
}

wait_for_db() {
    if ! command -v nc &> /dev/null; then
        log "❌ ERROR: El comando 'nc' (netcat) no se encuentra. "
        log "         Asegúrate de instalarlo en tu Dockerfile."
        exit 1
    fi
    local host_port=$(echo "$DATABASE_URL" | grep -oP '@\K[^/]+')
    local host=$(echo "$host_port" | cut -d: -f1)
    local port=$(echo "$host_port" | cut -d: -f2)
    log "Esperando a que la base de datos esté disponible en $host:$port..."
    until nc -z "$host" "$port"; do
        log "La base de datos no está lista. Reintentando en 2 segundos..."
        sleep 2
    done
    log "✅ ¡Conexión a la base de datos exitosa!"
}

# --- CORRECCIÓN: Se añade el flag '-c alembic.ini' para ser explícitos ---
run_migrations() {
    log "Ejecutando migraciones de la base de datos..."
    log "Verificando el estado del historial de Alembic..."
    
    # Se especifica explícitamente el archivo de configuración para evitar ambigüedades.
    local head_count=$(alembic -c alembic.ini heads 2>/dev/null | grep -c "(head)" || true)

    if [ "$head_count" -gt 1 ]; then
        log "❌ ERROR: Se detectaron múltiples cabezas en el historial de Alembic ($head_count)."
        log "   Alembic no puede continuar. Debes fusionar las cabezas manualmente."
        log "   Ejemplo: docker-compose exec app alembic -c alembic.ini merge <ID1> <ID2>"
        exit 1
    else
        log "✅ Historial de Alembic correcto. Procediendo con 'upgrade head'."
        # Se especifica explícitamente el archivo de configuración aquí también.
        alembic -c alembic.ini upgrade head
    fi
    
    log "✅ Migraciones completadas."
}

# --- Función Principal ---
main() {
    log "🚀 Iniciando configuración del entorno: ${ENVIRONMENT:-development}"
    
    check_env_vars
    
    if [ "$ENVIRONMENT" != "test" ]; then
        wait_for_db
    fi
    
    # --- MODO DIAGNÓSTICO: Migraciones aún desactivadas ---
    # Para poder arreglar el historial, mantenemos esto comentado por ahora.
    # run_migrations
    
    log "🚀 Iniciando aplicación Gunicorn... (MIGRACIONES OMITIDAS)"
    exec gunicorn \
        --bind "$HOST:$APP_PORT" \
        --workers "$WORKERS" \
        --timeout "$TIMEOUT" \
        --log-level "$LOG_LEVEL" \
        --worker-class uvicorn.workers.UvicornWorker \
        --access-logfile - \
        --error-logfile - \
        main:app
}

main "$@"