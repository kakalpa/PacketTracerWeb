#!/bin/bash
set -e

# If custom command passed, execute it
if [ "$#" -gt 0 ]; then
    exec "$@"
fi

# Ensure stable SECRET_KEY across all workers
SECRET_KEY_FILE="/app/.secret_key"
if [ -z "$SECRET_KEY" ] || [ "$SECRET_KEY" = "dev-key-change-in-production" ]; then
    if [ -f "$SECRET_KEY_FILE" ]; then
        export SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    else
        export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
        echo "$SECRET_KEY" > "$SECRET_KEY_FILE"
        chmod 600 "$SECRET_KEY_FILE"
    fi
fi
echo "Generated cryptographically secure random SECRET_KEY"

# Load certificate paths from environment or defaults
SSL_CERT="${SSL_CERT_PATH:-/etc/ssl/certs/server.crt}"
SSL_KEY="${SSL_KEY_PATH:-/etc/ssl/private/server.key}"

# Check alternate path (/project/ssl/) if default not found
if [ ! -f "$SSL_CERT" ] && [ -f "/project/ssl/server.crt" ]; then
    SSL_CERT="/project/ssl/server.crt"
fi
if [ ! -f "$SSL_KEY" ] && [ -f "/project/ssl/server.key" ]; then
    SSL_KEY="/project/ssl/server.key"
fi

# Standalone SSL mode (when running without Nginx reverse proxy)
USE_SSL=false
STANDALONE_SSL_LOWER=$(echo "${STANDALONE_SSL:-false}" | tr '[:upper:]' '[:lower:]')

if [ "$STANDALONE_SSL_LOWER" = "true" ] || [ "$STANDALONE_SSL_LOWER" = "1" ] || [ "$STANDALONE_SSL_LOWER" = "yes" ]; then
    if [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
        USE_SSL=true
    else
        echo "⚠️  STANDALONE_SSL is true, but SSL certificates were not found:"
        echo "   Cert: $SSL_CERT"
        echo "   Key:  $SSL_KEY"
        echo "   Falling back to HTTP on port 5000."
    fi
fi

if [ "$USE_SSL" = "true" ]; then
    echo "🔒 Starting pt-management with standalone SSL on port 5000..."
    echo "   Certificate: $SSL_CERT"
    echo "   Key:         $SSL_KEY"
    exec gunicorn \
        --bind 0.0.0.0:5000 \
        --workers 2 \
        --timeout 120 \
        --certfile="$SSL_CERT" \
        --keyfile="$SSL_KEY" \
        wsgi:app
else
    echo "🚀 Starting pt-management service on port 5000..."
    exec gunicorn \
        --bind 0.0.0.0:5000 \
        --workers 2 \
        --timeout 120 \
        wsgi:app
fi
