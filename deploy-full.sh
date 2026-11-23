#!/usr/bin/env bash

# Combined deployment wrapper
# This script runs the canonical deployment (deploy.sh) and then builds
# and starts the pt-management service so everything is ready in one command.

set -euo pipefail
cd "$(dirname "$0")"
ROOT_DIR="$(pwd)"
PT_MANAGEMENT_DIR="$ROOT_DIR/pt-management"

# Safe .env loader (no shell execution via source)
load_env_file() {
  local env_file="$1"
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*export[[:space:]]+(.*)$ ]] && line="${BASH_REMATCH[1]}"
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    key="${key//[[:space:]]/}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ "$val" =~ ^\"(.*)\"$ ]]; then
      val="${BASH_REMATCH[1]}"
    elif [[ "$val" =~ ^\'(.*)\'$ ]]; then
      val="${BASH_REMATCH[1]}"
    fi
    case "$key" in
      PRODUCTION_MODE|PUBLIC_IP|ENABLE_HTTPS|TLS_MODE|SERVER_NAME|\
      SSL_CERT_PATH|SSL_KEY_PATH|\
      CERTBOT_ENABLED|CERTBOT_DOMAIN|CERTBOT_EXTRA_DOMAINS|CERTBOT_EMAIL|\
      CERTBOT_CHALLENGE_TYPE|CERTBOT_STAGING|CERTBOT_AUTO_RENEW|CERTBOT_WEBROOT|\
      NGINX_GEOIP_ALLOW|NGINX_GEOIP_BLOCK|GEOIP_ALLOW_COUNTRIES|GEOIP_BLOCK_COUNTRIES|\
      NGINX_TRUSTED_IPS_OVERRIDE|\
      NGINX_RATE_LIMIT_ENABLE|NGINX_RATE_LIMIT_RATE|NGINX_RATE_LIMIT_BURST|NGINX_RATE_LIMIT_ZONE_SIZE|\
      PTADMIN_PASSWORD|DB_HOST|DB_USER|DB_PASSWORD|DB_NAME|NUM_PT|SHARED_HOST_PATH|STANDALONE_SSL)
        printf -v "$key" '%s' "$val"
        ;;
    esac
  done < "$env_file"
}

# Pre-create .env if missing so bind mounts never create an empty directory
if [[ ! -f "$ROOT_DIR/.env" ]]; then
  if [[ -f "$ROOT_DIR/.env.example" ]]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "ℹ️  Created .env from .env.example"
  else
    touch "$ROOT_DIR/.env"
    echo "ℹ️  Created empty .env"
  fi
fi

# Load environment configuration from .env safely
if [[ -f "$ROOT_DIR/.env" ]]; then
  load_env_file "$ROOT_DIR/.env"
  echo "ℹ️  Configuration loaded from .env"
fi

# Defaults - can be overridden via env or .env loaded by deploy.sh
PTADMIN_PASSWORD=${PTADMIN_PASSWORD:-IlovePT}
DB_HOST=${DB_HOST:-guacamole-mariadb}
DB_USER=${DB_USER:-ptdbuser}
DB_PASSWORD=${DB_PASSWORD:-ptdbpass}
DB_NAME=${DB_NAME:-guacamole_db}
NUM_PT=${NUM_PT:-2}
ENABLE_HTTPS=${ENABLE_HTTPS:-false}

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

# Ensure host SSL and Certbot directories exist
mkdir -p "$ROOT_DIR/ssl" \
         "$ROOT_DIR/certbot/conf" \
         "$ROOT_DIR/certbot/www/.well-known/acme-challenge"

# Connect core service containers to pt-stack network (ptvnc* instances stay isolated on internal pt-vncnet)
echo "Connecting core containers to pt-stack network..."
for container in guacamole-mariadb pt-guacd pt-guacamole pt-nginx1 pt-certbot; do
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

# Run container on pt-stack with Certbot directory mounts (use pt-nginx1 for external TLS)
docker run -d --name pt-management \
  --restart=unless-stopped \
  --network pt-stack \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$ROOT_DIR/shared:/shared" \
  -v "$ROOT_DIR/.env:/app/.env" \
  -v "$ROOT_DIR:/project" \
  -v "$ROOT_DIR/certbot/conf:/etc/letsencrypt" \
  -v "$ROOT_DIR/certbot/www:/var/www/certbot" \
  -e PTADMIN_PASSWORD="$PTADMIN_PASSWORD" \
  -e DB_HOST="$DB_HOST" \
  -e DB_USER="$DB_USER" \
  -e DB_PASSWORD="$DB_PASSWORD" \
  -e DB_NAME="$DB_NAME" \
  -e PROJECT_ROOT=/project \
  -e SHARED_HOST_PATH="$ROOT_DIR/shared" \
  -e ENABLE_HTTPS="$ENABLE_HTTPS" \
  -e STANDALONE_SSL="false" \
  pt-management:latest

# Also connect pt-management to ptnet network
docker network connect ptnet pt-management 2>/dev/null || true

# 4) Wait for pt-management health endpoint
echo "=== Step 4: Waiting for pt-management to become healthy ==="
MAX_WAIT=180
SLEEP_INTERVAL=3
elapsed=0
while true; do
  # First check if container is still running
  if ! docker ps --format '{{.Names}}' | grep -q '^pt-management$'; then
    echo "ERROR: pt-management container stopped unexpectedly"
    docker logs pt-management --tail 50
    exit 1
  fi
  
  # Try health endpoint (HTTPS with -k first if ENABLE_HTTPS=true, otherwise HTTP, with fallback)
  if [[ "$ENABLE_HTTPS" == "true" ]]; then
    http_code=$(curl -k -s -o /dev/null -w '%{http_code}' https://localhost:5000/health 2>/dev/null || echo "000")
  else
    http_code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:5000/health 2>/dev/null || echo "000")
  fi

  if [[ "$http_code" == "000" ]]; then
    http_code=$(curl -k -s -o /dev/null -w '%{http_code}' https://localhost:5000/health 2>/dev/null || curl -s -o /dev/null -w '%{http_code}' http://localhost:5000/health 2>/dev/null || echo "000")
  fi
  
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
    echo "  curl -k https://localhost:5000/health"
    echo ""
    break  # Don't exit - deployment might still be proceeding
  fi
done

echo "=== Deployment complete ==="
if [[ "$ENABLE_HTTPS" == "true" ]]; then
  echo "Access the main web UI at: https://localhost"
  echo "Access the management interface at: https://localhost:5000"
else
  echo "Access the main web UI at: http://localhost"
  echo "Access the management interface at: http://localhost:5000"
fi

echo "Tip: Tail pt-management logs: docker logs -f pt-management"

exit 0
