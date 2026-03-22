#!/usr/bin/env bash

# Combined deployment wrapper
# This script runs the canonical deployment (deploy.sh) and then builds
# and starts the pt-management service so everything is ready in one command.

set -euo pipefail
cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"
PT_MANAGEMENT_DIR="$ROOT_DIR/pt-management"

# Defaults - can be overridden via env or .env loaded by deploy.sh
PTADMIN_PASSWORD=${PTADMIN_PASSWORD:-IlovePT}
DB_HOST=${DB_HOST:-guacamole-mariadb}
DB_USER=${DB_USER:-ptdbuser}
DB_PASSWORD=${DB_PASSWORD:-ptdbpass}
DB_NAME=${DB_NAME:-guacamole_db}
NUM_PT=${NUM_PT:-2}

# HTTPS Configuration
# Auto-enable HTTPS if certificates exist (recommended for production)
DEFAULT_HTTPS="false"
if [ -f "$ROOT_DIR/ssl/server.crt" ] && [ -f "$ROOT_DIR/ssl/server.key" ]; then
    DEFAULT_HTTPS="true"
fi
ENABLE_HTTPS=${ENABLE_HTTPS:-$DEFAULT_HTTPS}
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/ssl/certs/server.crt}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/ssl/private/server.key}

usage() {
  cat <<EOF
Usage: $0 [recreate]

This wrapper will:
  1) Run ./deploy.sh [recreate] to deploy the Packet Tracer + Guacamole stack
  2) Build the pt-management Docker image
  3) Start the pt-management container and wait for it to be healthy

Pass the optional "recreate" argument to perform a full cleanup before deploying.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

# 1) Run canonical deploy script
echo "=== Step 1: Run deploy.sh ==="
if [[ -x "$ROOT_DIR/deploy.sh" ]]; then
  bash "$ROOT_DIR/deploy.sh" "${1:-}"
else
  echo "ERROR: deploy.sh not found or not executable in $ROOT_DIR"
  exit 1
fi

# Ensure Docker network exists (used by various containers)
if ! docker network ls --format '{{.Name}}' | grep -q '^pt-stack$'; then
  echo "Creating docker network 'pt-stack'"
  docker network create pt-stack || true
fi

# Ensure host shared directory exists and is writable so containers can mount it
if [[ ! -d "$ROOT_DIR/shared" ]]; then
  echo "Creating host shared directory: $ROOT_DIR/shared"
  mkdir -p "$ROOT_DIR/shared"
  chmod 777 "$ROOT_DIR/shared" || true
fi

# Connect all containers to pt-stack network for inter-container communication
echo "Connecting containers to pt-stack network..."
for container in guacamole-mariadb pt-guacd pt-guacamole pt-nginx1 ptvnc1 ptvnc2; do
  if docker ps -a --format '{{.Names}}' | grep -q "^${container}$"; then
    docker network connect pt-stack "$container" 2>/dev/null || echo "  (already connected: $container)"
  fi
done

# 2) Build pt-management image
echo "=== Step 2: Build pt-management image ==="
if [[ -d "$PT_MANAGEMENT_DIR" ]]; then
  docker build -t pt-management:latest "$PT_MANAGEMENT_DIR"
else
  echo "ERROR: pt-management directory not found: $PT_MANAGEMENT_DIR"
  exit 1
fi

# 3) Run pt-management container
echo "=== Step 3: Start pt-management container ==="
# Wait for Guacamole to be fully ready before starting pt-management
echo "Waiting for Guacamole to become ready (60 seconds)..."
sleep 60

# If container already exists and recreate requested, remove it
if [[ "${1:-}" == "recreate" ]]; then
  docker rm -f pt-management 2>/dev/null || true
fi

if docker ps -a --format '{{.Names}}' | grep -q '^pt-management$'; then
  echo "pt-management container already exists - stopping and removing"
  docker rm -f pt-management || true
fi

# Run container (use default bridge network so it can reach other containers by name)
# Prepare SSL mounts if HTTPS is enabled
SSL_MOUNTS=""
if [ "$ENABLE_HTTPS" = "true" ]; then
    if [ -f "./ssl/server.crt" ] && [ -f "./ssl/server.key" ]; then
        SSL_MOUNTS="-v $ROOT_DIR/ssl/server.crt:$SSL_CERT_PATH:ro -v $ROOT_DIR/ssl/server.key:$SSL_KEY_PATH:ro"
        echo "✓ HTTPS enabled: Mounting SSL certificates for pt-management"
    else
        echo "⚠ HTTPS enabled but certificates not found at ./ssl/server.crt and ./ssl/server.key"
        echo "  pt-management will fall back to HTTP"
    fi
else
    echo "ℹ HTTPS disabled for pt-management (set ENABLE_HTTPS=true to enable)"
fi

# Determine port mappings based on HTTPS
PORT_MAPPING="-p 5000:5000"
if [ "$ENABLE_HTTPS" = "true" ] && [ -f "./ssl/server.crt" ] && [ -f "./ssl/server.key" ]; then
    PORT_MAPPING="-p 5000:5000 -p 5443:5443"
    echo "✓ Port mapping: 5000 (HTTP redirect) and 5443 (HTTPS)"
else
    echo "ℹ Port mapping: 5000 only (HTTP)"
fi

docker run -d --name pt-management \
  --restart=unless-stopped \
  --network pt-stack \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$ROOT_DIR/shared:/shared" \
  -v "$ROOT_DIR/.env:/app/.env" \
  -v "$ROOT_DIR:/project" \
  $PORT_MAPPING \
  $SSL_MOUNTS \
  -e PTADMIN_PASSWORD="$PTADMIN_PASSWORD" \
  -e DB_HOST="$DB_HOST" \
  -e DB_USER="$DB_USER" \
  -e DB_PASSWORD="$DB_PASSWORD" \
  -e DB_NAME="$DB_NAME" \
  -e PROJECT_ROOT=/project \
  -e SHARED_HOST_PATH="$ROOT_DIR/shared" \
  -e ENABLE_HTTPS="$ENABLE_HTTPS" \
  -e SSL_CERT_PATH="$SSL_CERT_PATH" \
  -e SSL_KEY_PATH="$SSL_KEY_PATH" \
  pt-management:latest

# 4) Wait for pt-management health endpoint
echo "=== Step 4: Waiting for pt-management to become healthy ==="
MAX_WAIT=180
SLEEP_INTERVAL=3
elapsed=0

# Always use HTTP for health checks (port 5000, no SSL overhead)
# HTTPS (port 5443) is for user-facing traffic only
HEALTH_URL="http://localhost:5000/health"

while true; do
  # First check if container is still running
  if ! docker ps --format '{{.Names}}' | grep -q '^pt-management$'; then
    echo "ERROR: pt-management container stopped unexpectedly"
    docker logs pt-management --tail 50
    exit 1
  fi
  
  # Try health endpoint (HTTP only - no SSL warnings)
  http_code=$(curl -s -o /dev/null -w '%{http_code}' "$HEALTH_URL" 2>/dev/null || echo "000")
  
  # Accept 200, 503 (degraded but running), or 2xx
  if [[ "$http_code" =~ ^[2] ]]; then
    if [[ "$http_code" == "200" ]]; then
      echo "pt-management is fully healthy (HTTP 200)"
      break
    else
      echo "pt-management is responding (HTTP $http_code) - may need more time for database"
    fi
  fi
  
  echo "pt-management health check: HTTP $http_code (waiting...)"
  sleep $SLEEP_INTERVAL
  elapsed=$((elapsed + SLEEP_INTERVAL))
  
  if [[ $elapsed -ge $MAX_WAIT ]]; then
    echo ""
    echo "⚠ Timeout waiting for pt-management to become healthy (waited ${MAX_WAIT}s)"
    echo "Showing recent logs:"
    docker logs pt-management --tail 30
    echo ""
    echo "This may still be OK - database might be initializing. You can manually check:"
    echo "  docker logs pt-management"
    echo "  curl http://localhost:5000/health"
    echo ""
    break  # Don't exit - deployment might still be proceeding
  fi
done

echo "=== Deployment complete ==="
echo "Access the main web UI at: http://localhost"

if [ "$ENABLE_HTTPS" = "true" ] && [ -f "./ssl/server.crt" ] && [ -f "./ssl/server.key" ]; then
  echo "Access the management console at: https://localhost:5443 (admin port, HTTPS enabled)"
else
  echo "Access the management console at: http://localhost:5000 (admin port, HTTP)"
fi

echo "Tip: Tail pt-management logs: docker logs -f pt-management"

exit 0
