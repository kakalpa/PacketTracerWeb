#!/bin/bash

# Deployment script for PacketTracer + Guacamole stack
# This manually runs the docker commands from install.sh without system-level changes
# Usage: bash deploy.sh [recreate]
#   - No args: Deploy (fails if containers exist)
#   - recreate: Remove all containers/volumes and redeploy fresh

set -e

cd "$(dirname "$0")"
WORKDIR="$(pwd)"

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

# Pre-create .env if missing so Docker bind mounts never create a directory
if [ ! -f "$WORKDIR/.env" ]; then
    if [ -f "$WORKDIR/.env.example" ]; then
        cp "$WORKDIR/.env.example" "$WORKDIR/.env"
        echo -e "\e[36mℹ️  Created .env from .env.example\e[0m"
    else
        touch "$WORKDIR/.env"
        echo -e "\e[36mℹ️  Created empty .env\e[0m"
    fi
fi

# Load environment configuration from .env safely
if [ -f "$WORKDIR/.env" ]; then
    load_env_file "$WORKDIR/.env"
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
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/ssl/ptweb/server.crt}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/ssl/ptweb/server.key}

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
if [ "$ENABLE_HTTPS" = "true" ] || [ "$ENABLE_HTTPS" = "1" ]; then
    nginxport=443
    echo -e "\e[36mℹ️  HTTPS mode enabled (port 443)\e[0m"
else
    nginxport=80
    echo -e "\e[36mℹ️  HTTP mode (port 80)\e[0m"
fi

# Handle recreate argument
if [[ "${1:-}" == "recreate" ]]; then
    echo -e "\e[33m=== Recreate Mode: Cleaning up PacketTracer containers and volumes ===\e[0m"
    docker ps -a --format "{{.Names}}" | grep -E '^(guacamole-mariadb|pt-guacd|pt-guacamole|pt-nginx1|pt-management|pt-certbot|ptvnc.*)$' | xargs -r docker rm -f 2>/dev/null || true
    docker volume rm mariadb_data dbdump pt_opt 2>/dev/null || true
    docker network rm ptnet pt-stack pt-vncnet 2>/dev/null || true
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

# Always build pt-nginx and pt-certbot images (Docker layer cache keeps no-op builds fast)
echo "Building pt-nginx image..."
docker build -t pt-nginx ptweb-vnc/pt-nginx/
echo "Building pt-certbot image..."
docker build -t pt-certbot ptweb-vnc/pt-certbot/
echo ""

# Step 0.5: Download and setup GeoIP database (if GeoIP filtering is enabled)
echo -e "\e[32mStep 0.5. Setting up GeoIP Database\e[0m"
GEOIP_DIR="${WORKDIR}/geoip"
GEOIP_FILE="${GEOIP_DIR}/GeoIP.dat"

# Check if GeoIP filtering is enabled
if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_ALLOW" = "1" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; then
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

# Step 0.8: Create bridge networks (ptnet for core services, internal pt-vncnet for isolated VNC instances)
echo -e "\e[32mStep 0.8. Creating bridge networks 'ptnet' and 'pt-vncnet' (internal)\e[0m"
docker network create ptnet 2>/dev/null || echo "Network ptnet already exists"
docker network create --internal pt-vncnet 2>/dev/null || echo "Network pt-vncnet already exists"
echo ""

# Step 1: Start MariaDB
echo -e "\e[32mStep 1. Start MariaDB\e[0m"
docker run --name guacamole-mariadb --restart unless-stopped \
  --network ptnet \
  -v mariadb_data:/var/lib/mysql \
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
mkdir -p "${WORKDIR}/shared/instances"
mkdir -p "${WORKDIR}/shared/common"
mkdir -p "${WORKDIR}/shared/archive"
chmod 755 "${WORKDIR}/shared"
chmod 755 "${WORKDIR}/shared/instances"
chmod 777 "${WORKDIR}/shared/common"
chmod 700 "${WORKDIR}/shared/archive"

# Query Guacamole container IP and generate ptweb.conf
sleep 3
GUACAMOLE_IP=$(docker inspect pt-guacamole --format='{{.NetworkSettings.IPAddress}}' 2>/dev/null || echo "172.17.0.6")
GUACAMOLE_IP=$(echo "$GUACAMOLE_IP" | tr -d '
' | tr -d ' ')
echo -e "\033[36m  ✓ Guacamole IP: $GUACAMOLE_IP\033[0m"

# Nginx configuration generation is now handled by generate-nginx-conf.sh
# which dynamically generates both nginx.conf and ptweb.conf based on .env settings

# Ensure host SSL and Certbot directories exist before generating Nginx config
mkdir -p "${WORKDIR}/ssl" \
         "${WORKDIR}/certbot/conf" \
         "${WORKDIR}/certbot/www/.well-known/acme-challenge"

if [ "$ENABLE_HTTPS" = "true" ] || [ "$ENABLE_HTTPS" = "1" ]; then
    bash "${WORKDIR}/generate-ssl-cert.sh" --if-missing
fi

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
    INSTANCE_DIR="${WORKDIR}/shared/instances/ptvnc$i"
    mkdir -p "$INSTANCE_DIR"
    chmod 777 "$INSTANCE_DIR"

    # Generate unique 8-character VNC password per container (prevents student-to-student VNC access)
    INSTANCE_VNC_PASS=$(openssl rand -base64 12 2>/dev/null | tr -dc 'A-Za-z0-9' | head -c 8 || true)
    INSTANCE_VNC_PASS=${INSTANCE_VNC_PASS:-Cisco123}

    docker run -d \
      --name ptvnc$i --restart unless-stopped \
      --network pt-vncnet \
      --cpus=0.5 -m 2G --pids-limit 512 --ulimit nproc=2048 --ulimit nofile=1024 \
      --security-opt no-new-privileges:true \
      --dns=127.0.0.1 \
      -e "VNC_PASS=${INSTANCE_VNC_PASS}" \
      -v pt_opt:/opt/pt \
      --mount type=bind,source="${INSTANCE_DIR}",target=/shared,bind-propagation=rprivate \
      --mount type=bind,source="${WORKDIR}/shared/common",target=/shared_common,readonly,bind-propagation=rprivate \
      ptvnc
    sleep $i
done

# Create desktop and save symlinks for easy access to /shared and Course_Materials
echo -e "\e[32mCreating /shared, saves, and Course_Materials symlinks in containers\e[0m"
for ((i=1; i<=$numofPT; i++)); do
    docker exec ptvnc$i mkdir -p /home/ptuser/Desktop /home/ptuser/pt 2>/dev/null || true
    docker exec ptvnc$i ln -sfn /shared /home/ptuser/Desktop/shared 2>/dev/null || true
    docker exec ptvnc$i ln -sfn /shared /home/ptuser/Desktop/Personal_Saves 2>/dev/null || true
    docker exec ptvnc$i rm -rf /shared/shared 2>/dev/null || true
    docker exec ptvnc$i rm -rf /home/ptuser/pt/saves 2>/dev/null || true
    docker exec ptvnc$i ln -sfn /shared /home/ptuser/pt/saves 2>/dev/null || true
    docker exec ptvnc$i ln -sfn /shared_common /home/ptuser/Course_Materials 2>/dev/null || true
    docker exec ptvnc$i rm -f /home/ptuser/Desktop/Course_Materials 2>/dev/null || true
    if [ -f ptweb-vnc/libptsavehook.so ]; then
        docker cp ptweb-vnc/libptsavehook.so ptvnc$i:/usr/local/lib/libptsavehook.so 2>/dev/null || true
    fi
    docker exec ptvnc$i ln -sf /opt/pt/packettracer-launcher /opt/pt/packettracer 2>/dev/null || true
    if [ -f ptweb-vnc/app.png ]; then
        docker exec ptvnc$i mkdir -p /opt/pt/art /usr/share/pixmaps 2>/dev/null || true
        docker cp ptweb-vnc/app.png ptvnc$i:/opt/pt/art/app.png 2>/dev/null || true
        docker cp ptweb-vnc/app.png ptvnc$i:/usr/share/pixmaps/app.png 2>/dev/null || true
        docker cp ptweb-vnc/app.png ptvnc$i:/usr/share/pixmaps/packettracer.png 2>/dev/null || true
    fi
    docker exec ptvnc$i chown -R ptuser:ptuser /home/ptuser/Desktop 2>/dev/null || true
    docker exec ptvnc$i chown -h ptuser:ptuser /home/ptuser/Desktop/* 2>/dev/null || true
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
docker network connect pt-vncnet pt-guacd 2>/dev/null || true
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
  -e REMOTE_IP_VALVE_ENABLED=true \
  -e PROXY_ALLOWED_IPS_REGEX='172\.(1[6-9]|2[0-9]|3[0-1])\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|127\.0\.0\.1' \
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

# Mount GeoIP database if GeoIP filtering is enabled
GEOIP_ARGS=()
if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_ALLOW" = "1" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; then
    GEOIP_FILE="${WORKDIR}/geoip/GeoIP.dat"
    if [ -f "$GEOIP_FILE" ]; then
        GEOIP_ARGS+=(--mount "type=bind,source=${GEOIP_FILE},target=/usr/share/GeoIP/GeoIP.dat,readonly")
        echo -e "\033[36m  ✓ GeoIP filtering enabled: Mounting GeoIP database\033[0m"
    else
        echo -e "\033[33m  ⚠ GeoIP filtering enabled but database not found at: $GEOIP_FILE\033[0m"
    fi
fi

# Run nginx with directory mounts and unconditional ports 80/443/5000 on ptnet network
docker run --restart always --name pt-nginx1 \
  --network ptnet \
  --mount "type=bind,source=${WORKDIR}/ptweb-vnc/pt-nginx/nginx.conf,target=/etc/nginx/nginx.conf,readonly" \
  --mount "type=bind,source=${WORKDIR}/ptweb-vnc/pt-nginx/www,target=/usr/share/nginx/html,readonly" \
  --mount "type=bind,source=${WORKDIR}/ptweb-vnc/pt-nginx/conf,target=/etc/nginx/conf.d,readonly" \
  --mount "type=bind,source=${WORKDIR}/shared,target=/shared,readonly,bind-propagation=rprivate" \
  --mount "type=bind,source=${WORKDIR}/ssl,target=/etc/ssl/ptweb,readonly" \
  --mount "type=bind,source=${WORKDIR}/certbot/conf,target=/etc/letsencrypt,readonly" \
  --mount "type=bind,source=${WORKDIR}/certbot/www,target=/var/www/certbot,readonly" \
  "${GEOIP_ARGS[@]}" \
  -p 80:80 \
  -p 443:443 \
  -p 5000:5000 \
  -d pt-nginx

sleep 3
echo -e "\e[32m✓ Nginx started on ptnet network\e[0m"

# Step 5.5: Start Certbot automated renewal service
echo -e "\e[32mStep 5.5. Start Certbot renewal service\e[0m"
docker run -d --name pt-certbot \
  --restart unless-stopped \
  --network ptnet \
  --mount "type=bind,source=${WORKDIR}/certbot/conf,target=/etc/letsencrypt" \
  --mount "type=bind,source=${WORKDIR}/certbot/www,target=/var/www/certbot" \
  --mount "type=bind,source=${WORKDIR}/.env,target=/app/.env,readonly" \
  pt-certbot
echo -e "\e[32m✓ Certbot started on ptnet network\e[0m"

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
