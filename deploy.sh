#!/bin/bash

# Deployment script for PacketTracer + Guacamole stack
# This manually runs the docker commands from install.sh without system-level changes
# Usage: bash deploy.sh [recreate]
#   - No args: Deploy (fails if containers exist)
#   - recreate: Remove all containers/volumes and redeploy fresh

set -e

cd "$(dirname "$0")"
WORKDIR="$(pwd)"

# Load environment configuration from .env if it exists
if [ -f "$WORKDIR/.env" ]; then
    source "$WORKDIR/.env"
    echo -e "\e[36mℹ️  Configuration loaded from .env\e[0m"
fi

# Configuration from install.sh (with .env overrides)
dbuser="ptdbuser"
dbpass="ptdbpass"
dbname="guacamole_db"
numofPT=2
PTfile="CiscoPacketTracer.deb"

# SSL/HTTPS Configuration (from .env or defaults)
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/ssl/certs/server.crt}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/ssl/private/server.key}

# GeoIP Configuration (from .env or defaults)
NGINX_GEOIP_ALLOW=${NGINX_GEOIP_ALLOW:-false}
NGINX_GEOIP_BLOCK=${NGINX_GEOIP_BLOCK:-false}
GEOIP_ALLOW_COUNTRIES=${GEOIP_ALLOW_COUNTRIES:-US,CA,GB,AU,FI}
GEOIP_BLOCK_COUNTRIES=${GEOIP_BLOCK_COUNTRIES:-CN,RU,IR}

# Production Mode and Public IP Detection
PRODUCTION_MODE=${PRODUCTION_MODE:-false}
PUBLIC_IP=${PUBLIC_IP:-}

# Build trusted IPs list (always includes local/private networks)
NGINX_TRUSTED_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

# In production mode, detect and add public IP to trusted list
if [ "$PRODUCTION_MODE" = "true" ] || [ "$PRODUCTION_MODE" = "1" ]; then
    if [ -z "$PUBLIC_IP" ]; then
        echo -e "\e[36mℹ️  Production mode enabled. Detecting public IP...\e[0m"
        PUBLIC_IP=$(curl -s --max-time 5 https://ifconfig.co 2>/dev/null || echo "")
        if [ -n "$PUBLIC_IP" ]; then
            echo -e "\e[32m  ✓ Detected public IP: $PUBLIC_IP\e[0m"
        else
            echo -e "\e[33m  ⚠ Could not detect public IP (ifconfig.co unreachable). Proceeding with local-only access.\e[0m"
        fi
    else
        echo -e "\e[36mℹ️  Production mode: Using PUBLIC_IP from .env: $PUBLIC_IP\e[0m"
    fi
    
    # Add public IP to trusted list if detected
    if [ -n "$PUBLIC_IP" ]; then
        NGINX_TRUSTED_IPS="${NGINX_TRUSTED_IPS},$PUBLIC_IP"
        echo -e "\e[32m  ✓ Added public IP to trusted IPs\e[0m"
    fi
else
    echo -e "\e[36mℹ️  Development mode (PRODUCTION_MODE=false). Local IPs only.\e[0m"
fi

# Allow .env override of trusted IPs (if explicitly set)
if [ -n "${NGINX_TRUSTED_IPS_OVERRIDE:-}" ]; then
    NGINX_TRUSTED_IPS="$NGINX_TRUSTED_IPS_OVERRIDE"
    echo -e "\e[36mℹ️  Using NGINX_TRUSTED_IPS_OVERRIDE from .env\e[0m"
fi

echo -e "\e[36m  Trusted IPs for GeoIP bypass: $NGINX_TRUSTED_IPS\e[0m"

# Determine nginx port and setup based on HTTPS
if [ "$ENABLE_HTTPS" = "true" ]; then
    nginxport=443
    echo -e "\e[36mℹ️  HTTPS mode enabled (port 443)\e[0m"
else
    nginxport=80
    echo -e "\e[36mℹ️  HTTP mode (port 80)\e[0m"
fi

# Handle recreate argument
if [[ "${1:-}" == "recreate" ]]; then
    echo -e "\e[33m=== Recreate Mode: Cleaning up existing containers and volumes ===\e[0m"
    docker ps -a --format "{{.Names}}" | xargs -r docker rm -f 2>/dev/null || true
    docker volume ls --format "{{.Name}}" | xargs -r docker volume rm 2>/dev/null || true
    echo -e "\e[32m✓ Cleanup complete\e[0m"
    echo ""
fi

echo -e "\e[32m=== Starting Packet Tracer + Guacamole Deployment ===\e[0m"

# Check if .deb file exists (optional)
PTfile_found=false
if [[ -f "$PTfile" ]]; then
    PTfile_found=true
else
    candidate=$(ls -1 2>/dev/null | grep -E "PacketTracer|CiscoPacketTracer" | grep -E "\.deb$" | head -n1 || true)
    if [[ -n "$candidate" && -f "$candidate" ]]; then
        PTfile="$candidate"
        PTfile_found=true
    fi
fi

if [ "$PTfile_found" = true ]; then
    echo -e "\e[32m✓ Found PacketTracer .deb: $PTfile\e[0m"
else
    echo -e "\e[33m⚠ No PacketTracer .deb found - will build without it\e[0m"
    echo -e "\e[33m  To add it later, place the .deb in repo root and run: bash deploy.sh recreate\e[0m"
fi

# Build ptvnc Docker image (always rebuild to include/exclude .deb as needed)
echo -e "\e[32mStep 0. Building Docker images\e[0m"

# Copy .deb into ptweb-vnc directory for Docker COPY command (if it exists)
if [ "$PTfile_found" = true ] && [ -f "$PTfile" ]; then
    echo -e "\e[36mℹ️  Copying $PTfile to ptweb-vnc/ for Docker build...\e[0m"
    cp "$PTfile" "ptweb-vnc/CiscoPacketTracer.deb"
    echo -e "\e[32m✓ PacketTracer will be installed during Docker build\e[0m"
fi

echo "Building ptvnc image..."
docker build -t ptvnc ptweb-vnc/

# Clean up the copied .deb after build
rm -f "ptweb-vnc/CiscoPacketTracer.deb"
echo -e "\e[32m✓ ptvnc image built successfully\e[0m"

# Build pt-nginx Docker image if it doesn't exist
if ! docker image inspect pt-nginx:latest &>/dev/null; then
    echo "Building pt-nginx image..."
    docker build -t pt-nginx ptweb-vnc/pt-nginx/
else
    echo "pt-nginx image already exists, skipping build"
fi
echo ""

# Step 0.5: Download and setup GeoIP database (if GeoIP filtering is enabled)
echo -e "\e[32mStep 0.5. Setting up GeoIP Database\e[0m"
GEOIP_DIR="${WORKDIR}/geoip"
GEOIP_FILE="${GEOIP_DIR}/GeoIP.dat"

# Check if GeoIP filtering is enabled
if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ]; then
    echo -e "\e[36m  GeoIP filtering is enabled, checking database...\e[0m"
    
    # Create geoip directory
    mkdir -p "$GEOIP_DIR"
    
    # Check if GeoIP database already exists
    if [ -f "$GEOIP_FILE" ]; then
        echo -e "\e[32m  ✓ GeoIP database already exists: $GEOIP_FILE\e[0m"
    else
        echo -e "\e[36m  GeoIP database not found, downloading...\e[0m"
        
        # Download from DB-IP
        GEOIP_URL="https://mailfud.org/geoip-legacy/GeoIP.dat.gz"
        TEMP_GZ="${GEOIP_DIR}/GeoIP.dat.gz"
        
        if wget -q -O "$TEMP_GZ" "$GEOIP_URL" 2>/dev/null; then
            echo -e "\e[36m  ✓ Downloaded successfully, extracting...\e[0m"
            gunzip -f "$TEMP_GZ"
            # Rename to GeoIP.dat for nginx compatibility
            if [ -f "$GEOIP_FILE" ]; then
                true
                echo -e "\e[32m  ✓ GeoIP database extracted: $GEOIP_FILE\e[0m"
            fi
        else
            echo -e "\e[33m  ⚠ Warning: Failed to download GeoIP database from DB-IP\e[0m"
            echo -e "\e[33m  GeoIP filtering may not work properly\e[0m"
        fi
    fi
else
    echo -e "\e[33m  GeoIP filtering is disabled (NGINX_GEOIP_ALLOW=false, NGINX_GEOIP_BLOCK=false)\e[0m"
fi
echo ""

# Step 0.8: Create bridge network for containers
echo -e "\e[32mStep 0.8. Creating bridge network 'ptnet'\e[0m"
docker network create ptnet 2>/dev/null || echo "Network ptnet already exists"
echo ""

# Step 1: Start MariaDB
echo -e "\e[32mStep 1. Start MariaDB\e[0m"
docker run --name guacamole-mariadb --restart unless-stopped \
  --network ptnet \
  -v dbdump:/docker-entrypoint-initdb.d \
  -e MYSQL_ROOT_HOST=% \
  -e MYSQL_DATABASE=${dbname} \
  -e MYSQL_USER=${dbuser} \
  -e MYSQL_PASSWORD=${dbpass} \
  -e MYSQL_RANDOM_ROOT_PASSWORD=1 \
  -d mariadb:latest
sleep 10

# Step 2: Start ptvnc containers
echo -e "\e[32mStep 2. Start Packet Tracer VNC containers\e[0m"
mkdir -p "${WORKDIR}/shared"
chmod 777 "${WORKDIR}/shared"

# Query Guacamole container IP and generate ptweb.conf
sleep 3
GUACAMOLE_IP=$(docker inspect pt-guacamole --format='{{.NetworkSettings.IPAddress}}' 2>/dev/null || echo "172.17.0.6")
GUACAMOLE_IP=$(echo "$GUACAMOLE_IP" | tr -d '
' | tr -d ' ')
echo -e "\033[36m  ✓ Guacamole IP: $GUACAMOLE_IP\033[0m"

# Nginx configuration generation is now handled by generate-nginx-conf.sh
# which dynamically generates both nginx.conf and ptweb.conf based on .env settings

# Generate nginx configs with dynamic GeoIP maps and location blocks
echo -e "\033[32m  Generating dynamic nginx configuration...\033[0m"
bash "${WORKDIR}/ptweb-vnc/pt-nginx/generate-nginx-conf.sh"
echo -e "\033[32m  ✓ Generated nginx.conf and ptweb.conf with GeoIP filtering\033[0m"

# CPU-based rendering - no GPU pass-through needed
# Packet Tracer uses Mesa llvmpipe for software OpenGL rendering
echo "ℹ️  Using CPU-based software rendering (no GPU pass-through)"

# CPU-based rendering - no GPU pass-through needed
# Packet Tracer uses Mesa llvmpipe for software OpenGL rendering
echo "ℹ️  Using CPU-based software rendering (no GPU pass-through)"

for ((i=1; i<=$numofPT; i++)); do
    docker run -d \
      --name ptvnc$i --restart unless-stopped \
      --network ptnet \
      --cpus=0.5 -m 2G --ulimit nproc=2048 --ulimit nofile=1024 \
      --dns=127.0.0.1 \
      -v pt_opt:/opt/pt \
      --mount type=bind,source="${WORKDIR}/shared",target=/shared,bind-propagation=rprivate \
      ptvnc
    sleep $i
done

# Create desktop symlinks for easy access to /shared
echo -e "\e[32mCreating /shared symlinks on Desktop\e[0m"
for ((i=1; i<=$numofPT; i++)); do
    docker exec ptvnc$i mkdir -p /home/ptuser/Desktop 2>/dev/null || true
    docker exec ptvnc$i ln -sf /shared /home/ptuser/Desktop/shared 2>/dev/null || true
done
sleep 2

# Step 3: Import Database
echo -e "\e[32mStep 3. Import Guacamole Database\e[0m"
sleep 20
docker exec -i guacamole-mariadb mariadb -u${dbuser} -p${dbpass} < ptweb-vnc/db-dump.sql

# Step 4: Start Guacamole services
echo -e "\e[32mStep 4. Start Guacamole services\e[0m"

docker run --name pt-guacd --restart always \
  --network ptnet \
  -d guacamole/guacd:latest
sleep 20

# Get guacd IP for Guacamole configuration
GUACD_IP=$(docker inspect pt-guacd --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | tr -d ' ')
echo -e "\e[36m  ✓ guacd IP: $GUACD_IP\e[0m"

docker run --name pt-guacamole --restart always \
  --network ptnet \
  -e MYSQL_HOSTNAME=guacamole-mariadb \
  -e MYSQL_DATABASE=${dbname} \
  -e MYSQL_USER=${dbuser} \
  -e MYSQL_PASSWORD=${dbpass} \
  -e GUACAMOLE_GUACD_HOSTNAME=pt-guacd \
  -e GUACAMOLE_GUACD_PORT=4822 \
  -d guacamole/guacamole

# Step 5: Start Nginx
echo -e "\e[32mStep 5. Start Nginx web server\e[0m"
mkdir -p "${WORKDIR}/shared"
chmod 777 "${WORKDIR}/shared"

# Query Guacamole container IP (if it wasn't already determined)
if [ -z "$GUACAMOLE_IP" ]; then
    sleep 3
    GUACAMOLE_IP=$(docker inspect pt-guacamole --format='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' | tr -d ' ')
fi
echo -e "\033[36m  ✓ Guacamole IP: $GUACAMOLE_IP\033[0m"

# Regenerate nginx configs dynamically from .env settings
echo -e "\033[32m  Regenerating nginx configurations...\033[0m"
bash "${WORKDIR}/ptweb-vnc/pt-nginx/generate-nginx-conf.sh"
echo -e "\033[32m  ✓ Regenerated nginx.conf and ptweb.conf\033[0m"

# Mount SSL certificates if HTTPS is enabled
SSL_MOUNTS=""
if [ "$ENABLE_HTTPS" = "true" ]; then
    # Extract directory paths from certificate and key paths
    SSL_CERT_DIR=$(dirname "$SSL_CERT_PATH")
    SSL_KEY_DIR=$(dirname "$SSL_KEY_PATH")
    
    # Mount certificate files if they exist on host
    if [ -f "./ssl/server.crt" ]; then
        SSL_MOUNTS="$SSL_MOUNTS --mount type=bind,source=\"$(pwd)/ssl/server.crt\",target=$SSL_CERT_PATH,readonly"
    fi
    if [ -f "./ssl/server.key" ]; then
        SSL_MOUNTS="$SSL_MOUNTS --mount type=bind,source=\"$(pwd)/ssl/server.key\",target=$SSL_KEY_PATH,readonly"
    fi
    echo -e "\033[36m  ✓ HTTPS enabled: Mounting SSL certificates\033[0m"
fi

# Mount GeoIP database if GeoIP filtering is enabled
GEOIP_MOUNTS=""
if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ]; then
    GEOIP_FILE="${WORKDIR}/geoip/GeoIP.dat"
    if [ -f "$GEOIP_FILE" ]; then
        GEOIP_MOUNTS="--mount type=bind,source=\"$GEOIP_FILE\",target=/usr/share/GeoIP/GeoIP.dat,readonly"
        echo -e "\033[36m  ✓ GeoIP filtering enabled: Mounting GeoIP database\033[0m"
    else
        echo -e "\033[33m  ⚠ GeoIP filtering enabled but database not found at: $GEOIP_FILE\033[0m"
    fi
fi

# Run nginx with appropriate port and SSL mounts on ptnet network
eval "docker run --restart always --name pt-nginx1 \
  --network ptnet \
  --mount type=bind,source=\"${WORKDIR}/ptweb-vnc/pt-nginx/nginx.conf\",target=/etc/nginx/nginx.conf,readonly \
  --mount type=bind,source=\"${WORKDIR}/ptweb-vnc/pt-nginx/www\",target=/usr/share/nginx/html,readonly \
  --mount type=bind,source=\"${WORKDIR}/ptweb-vnc/pt-nginx/conf\",target=/etc/nginx/conf.d,readonly \
  --mount type=bind,source=\"${WORKDIR}/shared\",target=/shared,readonly,bind-propagation=rprivate \
  $SSL_MOUNTS \
  $GEOIP_MOUNTS \
  -p 80:80 \
  $([ "$ENABLE_HTTPS" = "true" ] && echo "-p 443:443") \
  -d pt-nginx"

sleep 3
echo -e "\e[32m✓ Nginx started on ptnet network\e[0m"

# Step 6: Generate dynamic connections
echo -e "\e[32mStep 6. Generating dynamic Guacamole connections\e[0m"
sleep 3
bash generate-dynamic-connections.sh $numofPT || echo "Warning: generate-dynamic-connections failed (continuing)"
sleep 2

# Verify PacketTracer installation in containers (it was installed during Docker build if .deb was provided)
echo ""
echo -e "\e[32mStep 7. Verifying PacketTracer installation\e[0m"
for ((i=1; i<=$numofPT; i++)); do
    if docker exec ptvnc$i test -x /opt/pt/packettracer.AppImage 2>/dev/null || \
       docker exec ptvnc$i test -x /opt/pt/packettracer-launcher 2>/dev/null; then
        echo -e "\e[32m  ✓ ptvnc$i: PacketTracer ready\e[0m"
    else
        echo -e "\e[33m  ⚠ ptvnc$i: PacketTracer not installed (provide .deb and rebuild)\e[0m"
    fi
done
echo ""

echo -e "\e[32m=== Deployment Complete (installer not waited-on) ===\e[0m"
echo "Services Status:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo -e "\e[36m════════════════════════════════════════════════════════════════\e[0m"
echo -e "\e[32mAccess the web interface at: http://localhost\e[0m"
echo -e "\e[36m════════════════════════════════════════════════════════════════\e[0m"
echo ""
echo "Available Packet Tracer connections:"
for ((i=1; i<=$numofPT; i++)); do
    echo "  - pt$(printf "%02d" $i)"
done
echo ""
echo -e "\e[32m✓ SUCCESS - Deployment started. Run runtime installer manually if needed.\e[0m"
echo ""
