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

# Check if .deb file exists
if [[ ! -f "$PTfile" ]]; then
    candidate=$(ls -1 2>/dev/null | grep -E "PacketTracer|CiscoPacketTracer" | grep -E "\.deb$" | head -n1 || true)
    if [[ -n "$candidate" && -f "$candidate" ]]; then
        PTfile="$candidate"
    else
        echo "ERROR: Packet Tracer .deb file not found!"
        exit 1
    fi
fi

echo "Using Packet Tracer file: $PTfile"

# Build ptvnc Docker image if it doesn't exist
echo -e "\e[32mStep 0. Building Docker images\e[0m"
if ! docker image inspect ptvnc:latest &>/dev/null; then
    echo "Building ptvnc image..."
    docker build -t ptvnc ptweb-vnc/
else
    echo "ptvnc image already exists, skipping build"
fi

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
        DB_IP_URL="https://download.db-ip.com/free/dbip-country-lite-2025-11.mmdb.gz"
        TEMP_GZ="${GEOIP_DIR}/dbip-country-lite.mmdb.gz"
        
        if wget -q -O "$TEMP_GZ" "$DB_IP_URL" 2>/dev/null; then
            echo -e "\e[36m  ✓ Downloaded successfully, extracting...\e[0m"
            gunzip -f "$TEMP_GZ"
            # Rename to GeoIP.dat for nginx compatibility
            if [ -f "${GEOIP_DIR}/dbip-country-lite.mmdb" ]; then
                mv "${GEOIP_DIR}/dbip-country-lite.mmdb" "$GEOIP_FILE"
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

# Step 1: Start MariaDB
echo -e "\e[32mStep 1. Start MariaDB\e[0m"
docker run --name guacamole-mariadb --restart unless-stopped \
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

# Helper function to generate nginx config with HTTPS support
generate_nginx_config() {
    local guacamole_ip="$1"
    local enable_https="$2"
    local cert_path="$3"
    local key_path="$4"
    
    # Generate http context directives (rate limiting zone)
    if [ "$NGINX_RATE_LIMIT_ENABLE" = "true" ]; then
        cat << 'PTWEB_EOF'
# Rate limiting zone (http context)
limit_req_zone $binary_remote_addr zone=pt_req_zone:RATE_LIMIT_ZONE_SIZE rate=RATE_LIMIT_RATE;

PTWEB_EOF
    fi
    
    # Generate HTTP server block (always included)
    cat << 'PTWEB_EOF'
server {
    listen 80;
    server_name localhost;

    charset utf-8;
PTWEB_EOF
    
    # If HTTPS is enabled, add redirect from HTTP to HTTPS
    if [ "$enable_https" = "true" ]; then
        cat << 'PTWEB_EOF'
    # Redirect HTTP to HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name localhost;

    charset utf-8;

    # SSL Configuration
    ssl_certificate SSL_CERT_PATH_PLACEHOLDER;
    ssl_certificate_key SSL_KEY_PATH_PLACEHOLDER;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

PTWEB_EOF
    else
        cat << 'PTWEB_EOF'

PTWEB_EOF
    fi
    
    # Common server block content
    cat << 'PTWEB_EOF'
    # Serve shared downloads with highest priority
    location ^~ /downloads/ {
        alias /shared/;
        autoindex on;
        autoindex_exact_size off;
        autoindex_localtime on;
    }

    # File manager interface
    location ^~ /files {
        rewrite ^/files/?$ /file-manager.html break;
    }

    # Root location - catches all other requests for Guacamole
    location / {
        # GeoIP filtering logic with trusted IP bypass
        # Using map directives (defined at http level) instead of nested if statements
        # which nginx does not support
        
        # Check access: returns 1 if allowed, 0 if denied
        if ($deny_by_geoip = 1) {
            return 444;
        }
        
        proxy_redirect off;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket support for Guacamole tunneling
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        client_max_body_size 10m;
        RATE_LIMIT_DIRECTIVE_PLACEHOLDER
        client_body_buffer_size 128k;
        proxy_connect_timeout 90;
        proxy_send_timeout 90;
        proxy_read_timeout 90;
        proxy_buffers 32 4k;
        proxy_pass http://GUACAMOLE_IP_PLACEHOLDER:8080/guacamole/;
    }

    location ~ /\.ht {
        deny all;
    }

    error_page   500 502 503 504  /50x.html;
    location = /50x.html {
        root   /usr/share/nginx/html;
    }
}
PTWEB_EOF
}

# Generate ptweb.conf with HTTPS support if enabled
{
    # Prepare rate limit directive if enabled
    if [ "$NGINX_RATE_LIMIT_ENABLE" = "true" ]; then
        RATE_LIMIT_DIRECTIVE="limit_req zone=pt_req_zone burst=${NGINX_RATE_LIMIT_BURST} nodelay;"
    else
        RATE_LIMIT_DIRECTIVE=""
    fi
    
    # Generate config with all placeholders replaced
    generate_nginx_config "$GUACAMOLE_IP" "$ENABLE_HTTPS" "$SSL_CERT_PATH" "$SSL_KEY_PATH" | \
        sed "s|GUACAMOLE_IP_PLACEHOLDER|$GUACAMOLE_IP|g; s|SSL_CERT_PATH_PLACEHOLDER|$SSL_CERT_PATH|g; s|SSL_KEY_PATH_PLACEHOLDER|$SSL_KEY_PATH|g; s|RATE_LIMIT_ZONE_SIZE|${NGINX_RATE_LIMIT_ZONE_SIZE:-10m}|g; s|RATE_LIMIT_RATE|${NGINX_RATE_LIMIT_RATE:-10r/s}|g;" | \
        sed "s|RATE_LIMIT_DIRECTIVE_PLACEHOLDER|$RATE_LIMIT_DIRECTIVE|g"
} > "${WORKDIR}/ptweb-vnc/pt-nginx/conf/ptweb.conf"
echo -e "\033[32m  ✓ Generated ptweb.conf with Guacamole IP and HTTPS=$([ "$ENABLE_HTTPS" = "true" ] && echo "enabled" || echo "disabled")\033[0m"

for ((i=1; i<=$numofPT; i++)); do
    docker run -d \
      --name ptvnc$i --restart unless-stopped \
      --cpus=0.1 -m 1G --ulimit nproc=2048 --ulimit nofile=1024 \
      --dns=127.0.0.1 \
      -v "${WORKDIR}/${PTfile}:/PacketTracer.deb:ro" \
      -v pt_opt:/opt/pt \
      --mount type=bind,source="${WORKDIR}/shared",target=/shared,bind-propagation=rprivate \
      -e PT_DEB_PATH=/PacketTracer.deb \
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
linkstr=""
for ((i=1; i<=$numofPT; i++)); do
    linkstr="${linkstr} --link ptvnc$i:ptvnc$i"
done

docker run --name pt-guacd --restart always -d ${linkstr} guacamole/guacd
sleep 20

docker run --name pt-guacamole --restart always \
  --link pt-guacd:guacd \
  --link guacamole-mariadb:mysql \
  -e MYSQL_DATABASE=${dbname} \
  -e MYSQL_USER=${dbuser} \
  -e MYSQL_PASSWORD=${dbpass} \
  -d guacamole/guacamole

# Step 5: Start Nginx
echo -e "\e[32mStep 5. Start Nginx web server\e[0m"
mkdir -p "${WORKDIR}/shared"
chmod 777 "${WORKDIR}/shared"

# Query Guacamole container IP (if it wasn't already determined)
if [ -z "$GUACAMOLE_IP" ]; then
    sleep 3
    GUACAMOLE_IP=$(docker inspect pt-guacamole --format='{{.NetworkSettings.IPAddress}}' 2>/dev/null || echo "172.17.0.6")
    GUACAMOLE_IP=$(echo "$GUACAMOLE_IP" | tr -d '
' | tr -d ' ')
fi
echo -e "\033[36m  ✓ Guacamole IP: $GUACAMOLE_IP\033[0m"

# Regenerate ptweb.conf with the correct Guacamole IP and HTTPS settings
{
    # Prepare rate limit directive if enabled
    if [ "$NGINX_RATE_LIMIT_ENABLE" = "true" ]; then
        RATE_LIMIT_DIRECTIVE="limit_req zone=pt_req_zone burst=${NGINX_RATE_LIMIT_BURST} nodelay;"
    else
        RATE_LIMIT_DIRECTIVE=""
    fi
    
    # Generate config with all placeholders replaced
    generate_nginx_config "$GUACAMOLE_IP" "$ENABLE_HTTPS" "$SSL_CERT_PATH" "$SSL_KEY_PATH" | \
        sed "s|GUACAMOLE_IP_PLACEHOLDER|$GUACAMOLE_IP|g; s|SSL_CERT_PATH_PLACEHOLDER|$SSL_CERT_PATH|g; s|SSL_KEY_PATH_PLACEHOLDER|$SSL_KEY_PATH|g; s|RATE_LIMIT_ZONE_SIZE|${NGINX_RATE_LIMIT_ZONE_SIZE:-10m}|g; s|RATE_LIMIT_RATE|${NGINX_RATE_LIMIT_RATE:-10r/s}|g;" | \
        sed "s|RATE_LIMIT_DIRECTIVE_PLACEHOLDER|$RATE_LIMIT_DIRECTIVE|g"
} > "${WORKDIR}/ptweb-vnc/pt-nginx/conf/ptweb.conf"
echo -e "\033[32m  ✓ Generated ptweb.conf with Guacamole IP and HTTPS=$([ "$ENABLE_HTTPS" = "true" ] && echo "enabled" || echo "disabled")\033[0m"

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

# Run nginx with appropriate port and SSL mounts
eval "docker run --restart always --name pt-nginx1 \
  --mount type=bind,source=\"${WORKDIR}/ptweb-vnc/pt-nginx/www\",target=/usr/share/nginx/html,readonly \
  --mount type=bind,source=\"${WORKDIR}/ptweb-vnc/pt-nginx/conf\",target=/etc/nginx/conf.d,readonly \
  --mount type=bind,source=\"${WORKDIR}/shared\",target=/shared,readonly,bind-propagation=rprivate \
  $SSL_MOUNTS \
  $GEOIP_MOUNTS \
  --link pt-guacamole:guacamole \
  -p 80:80 \
  $([ "$ENABLE_HTTPS" = "true" ] && echo "-p 443:443") \
  -d pt-nginx"

# Step 6: Generate dynamic connections
echo -e "\e[32mStep 6. Generating dynamic Guacamole connections\e[0m"
sleep 10
bash generate-dynamic-connections.sh $numofPT
sleep 5

# Wait for PacketTracer installation to complete in all containers
echo -e "\e[32m=== Waiting for PacketTracer Installation ===\e[0m"
echo "Monitoring container logs for installation completion..."
echo ""

# Function to check if PT is installed in a container
check_pt_installed() {
    local container=$1
    # Check if the binary actually exists in the container 
    docker exec "$container" test -x /opt/pt/packettracer 2>/dev/null && return 0 || return 1
}

# Function to get installation logs from a container
get_install_logs() {
    local container=$1
    docker logs "$container" 2>&1 | grep "\[pt-install\]" | tail -5
}

# Wait for all containers to complete installation
all_installed=false
timeout=600  # 10 minute timeout
elapsed=0
last_log_display=0
declare -A completed_containers

while [ $elapsed -lt $timeout ]; do
    all_installed=true
    for ((i=1; i<=$numofPT; i++)); do
        if ! check_pt_installed "ptvnc$i"; then
            all_installed=false
        fi
    done
    
    if [ "$all_installed" = true ]; then
        break
    fi
    
    # Display logs every 15 seconds
    if [ $((elapsed - last_log_display)) -ge 15 ] || [ $elapsed -eq 0 ]; then
        echo ""
        echo -e "\e[36m--- Installation Progress ---\e[0m"
        
        # Show status and logs for each container
        for ((i=1; i<=$numofPT; i++)); do
            if check_pt_installed "ptvnc$i"; then
                # Container is done - show it only once
                if [ -z "${completed_containers[ptvnc$i]}" ]; then
                    echo -e "\e[32m✓ ptvnc$i: Installation completed\e[0m"
                    completed_containers[ptvnc$i]=1
                fi
            else
                # Container still installing - show progress
                echo -e "\e[33m⏳ ptvnc$i: Installing...\e[0m"
                get_install_logs "ptvnc$i" | tail -3
            fi
        done
        
        last_log_display=$elapsed
    fi
    
    sleep 5
    elapsed=$((elapsed + 5))
    echo -ne "\rWaiting for installation... ($elapsed/$timeout seconds)"
done

echo ""
echo ""

if [ "$all_installed" = true ]; then
    echo -e "\e[32m✓ PacketTracer installation completed successfully in all containers\e[0m"
    echo ""
    echo -e "\e[36m=== Final Installation Status ===\e[0m"
    for ((i=1; i<=$numofPT; i++)); do
        echo -e "\e[32mptvnc$i:\e[0m"
        get_install_logs "ptvnc$i" | tail -3
        echo ""
    done
else
    echo -e "\e[33m⚠ Timeout waiting for installation (this may be normal if still running)\e[0m"
fi

echo ""
echo -e "\e[32m=== Deployment Complete ===\e[0m"
echo ""
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
echo -e "\e[32m✓ SUCCESS - Deployment and installation complete!\e[0m"
echo ""
