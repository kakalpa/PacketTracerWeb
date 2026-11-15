#!/bin/bash
# Start Flask with gunicorn and SSL on port 5000

SSL_CERT="${SSL_CERT_PATH:-/etc/ssl/certs/server.crt}"
SSL_KEY="${SSL_KEY_PATH:-/etc/ssl/private/server.key}"

# Check alternate paths if default not found
if [ ! -f "$SSL_CERT" ] && [ -f "../ssl/server.crt" ]; then
    SSL_CERT="../ssl/server.crt"
elif [ ! -f "$SSL_CERT" ] && [ -f "/project/ssl/server.crt" ]; then
    SSL_CERT="/project/ssl/server.crt"
fi

if [ ! -f "$SSL_KEY" ] && [ -f "../ssl/server.key" ]; then
    SSL_KEY="../ssl/server.key"
elif [ ! -f "$SSL_KEY" ] && [ -f "/project/ssl/server.key" ]; then
    SSL_KEY="/project/ssl/server.key"
fi

echo "Starting pt-management with SSL on port 5000..."
echo "Certificate: $SSL_CERT"
echo "Key:         $SSL_KEY"

exec gunicorn \
  --bind 0.0.0.0:5000 \
  --workers 2 \
  --timeout 120 \
  --certfile="$SSL_CERT" \
  --keyfile="$SSL_KEY" \
  wsgi:app
