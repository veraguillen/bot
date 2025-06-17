#!/bin/bash
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
        log "❌ ERROR: El comando 'nc' (netcat) no se encuentra. Asegúrate de instalarlo en tu Dockerfile."
        exit 1
    fi

    # --- MEJORA DE ROBUSTEZ: Usando 'sed' para parsear la URL ---
    # Este método es más resistente a diferentes formatos de URL.
    local db_uri_no_proto=${DATABASE_URL#*@}
    local host=$(echo "$db_uri_no_proto" | sed -E 's/:[0-9]+.*//')
    local port=$(echo "$db_uri_no_proto" | sed -E 's/.*:([0-9]+).*/\1/')

    # Verificación de que el parseo funcionó
    if [ -z "$host" ] || [ -z "$port" ]; then
        log "❌ ERROR: No se pudo extraer el host y el puerto de DATABASE_URL."
        log "   Valor actual de DATABASE_URL: $DATABASE_URL"
        exit 1
    fi

    log "Esperando a que la base de datos esté disponible en $host:$port..."
    
    until nc -z "$host" "$port"; do
        log "La base de datos no está lista. Reintentando en 2 segundos..."
        sleep 2
    done
    
    log "✅ ¡Conexión a la base de datos exitosa!"
}

run_migrations() {
    log "Ejecutando migraciones de la base de datos..."
    log "Verificando el estado del historial de Alembic..."
    local head_count=$(alembic -c alembic.ini heads 2>/dev/null | grep -c "(head)" || true)

    if [ "$head_count" -gt 1 ]; then
        log "❌ ERROR: Se detectaron múltiples cabezas en el historial de Alembic ($head_count)."
        log "   Debes fusionarlas manualmente."
        exit 1
    else
        log "✅ Historial de Alembic correcto. Procediendo con 'upgrade head'."
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
    
    run_migrations
    
    log "🚀 Iniciando aplicación Gunicorn en $HOST:$APP_PORT con $WORKERS workers..."
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