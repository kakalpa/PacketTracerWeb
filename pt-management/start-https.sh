#!/bin/bash
# Start Flask with gunicorn and SSL on port 8080

gunicorn \
  --bind 0.0.0.0:8080 \
  --workers 2 \
  --timeout 120 \
  --certfile=/etc/ssl/certs/server.crt \
  --keyfile=/etc/ssl/private/server.key \
  wsgi:app
