#!/bin/bash

# Deployment script for PacketTracer + Guacamole stack
# This manually runs the docker commands from install.sh without system-level changes
# Enhanced to support secure setup with credentials, HTTPS, GeoIP, and download auth
# Usage: bash deploy.sh [recreate]

set -e

cd "$(dirname "$0")"

# Check for recreate argument
RECREATE_MODE="${1:-}"

# ============================================================================
# RECREATE MODE: Remove all containers and volumes, then restart fresh
# ============================================================================
if [[ "$RECREATE_MODE" == "recreate" ]]; then
    echo -e "\e[33m⚠️  RECREATE MODE: Removing all containers and volumes...\e[0m"
    echo ""
    
    echo "Stopping all containers..."
    docker stop $(docker ps -q) 2>/dev/null || true
    
    echo "Removing containers..."
    docker rm guacamole-mariadb ptvnc1 ptvnc2 ptvnc3 ptvnc4 ptvnc5 pt-guacd pt-guacamole pt-nginx1 2>/dev/null || true
    
    echo "Removing volumes..."
    docker volume rm dbdump pt_opt 2>/dev/null || true
    
    echo "Removing initialization cache..."
    rm -f .env.init
    
    # Check if .env.secure exists before removing it
    if [[ -f ".env.secure" ]]; then
        echo "Backing up .env.secure for new deployment..."
        cp .env.secure .env.secure.backup.$(date +%s)
    else
        echo "No existing credentials found, new ones will be generated."
    fi
    
    echo -e "\e[32m✓ Cleanup complete. Starting fresh deployment...\e[0m"
    echo ""
    
    # Continue with fresh deployment
    FRESH_START="true"
else
    FRESH_START="false"
fi

# ============================================================================
# LOAD SECURE CREDENTIALS
# ============================================================================
# Check if .env.secure exists (from secure-setup.sh)
if [[ -f ".env.secure" ]] && [[ "$FRESH_START" != "true" ]]; then
    echo -e "\e[32m✓ Loading secure credentials from .env.secure\e[0m"
    source .env.secure
    
    # Use credentials from .env.secure
    dbuser="${DB_USER}"
    dbpass="${DB_USER_PASSWORD}"
    dbname="${DB_NAME}"
    DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}"
    VNC_PASSWORD="${VNC_PASSWORD}"
    GUACAMOLE_PASSWORD="${GUACAMOLE_PASSWORD}"
    DOWNLOAD_AUTH_USER="${DOWNLOAD_AUTH_USER}"
    DOWNLOAD_AUTH_PASSWORD="${DOWNLOAD_AUTH_PASSWORD}"
    ENABLE_HTTPS="${ENABLE_HTTPS:-false}"
    ENABLE_GEOIP="${ENABLE_GEOIP:-false}"
    REQUIRE_DOWNLOAD_AUTH="${REQUIRE_DOWNLOAD_AUTH:-false}"
    nginxport="${NGINX_PORT:-80}"
else
    echo -e "\e[33m⚠️  .env.secure not found. Running secure-setup.sh first...\e[0m"
    # Don't force NONINTERACTIVE mode - let the user configure interactively
    bash secure-setup.sh
    source .env.secure
    
    # Use credentials from .env.secure
    dbuser="${DB_USER}"
    dbpass="${DB_USER_PASSWORD}"
    dbname="${DB_NAME}"
    DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}"
    VNC_PASSWORD="${VNC_PASSWORD}"
    GUACAMOLE_PASSWORD="${GUACAMOLE_PASSWORD}"
    DOWNLOAD_AUTH_USER="${DOWNLOAD_AUTH_USER}"
    DOWNLOAD_AUTH_PASSWORD="${DOWNLOAD_AUTH_PASSWORD}"
    ENABLE_HTTPS="${ENABLE_HTTPS:-false}"
    ENABLE_GEOIP="${ENABLE_GEOIP:-false}"
    REQUIRE_DOWNLOAD_AUTH="${REQUIRE_DOWNLOAD_AUTH:-false}"
    nginxport="${NGINX_PORT:-80}"
fi

# ============================================================================
# DEPLOYMENT CONFIGURATION
# ============================================================================
numofPT=2
PTfile="CiscoPacketTracer.deb"

echo -e "\e[32m=== Starting Packet Tracer + Guacamole Deployment ===\e[0m"
echo ""
echo "Deployment Configuration:"
echo "  Database User: $dbuser"
echo "  Database Name: $dbname"
echo "  PT Instances: $numofPT"
echo "  HTTPS Enabled: $ENABLE_HTTPS"
echo "  GeoIP Enabled: $ENABLE_GEOIP"
echo "  Download Auth: $REQUIRE_DOWNLOAD_AUTH"
echo ""

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

# Step 1: Start MariaDB
echo -e "\e[32mStep 1. Start MariaDB\e[0m"
docker run --name guacamole-mariadb --restart unless-stopped \
  -v dbdump:/docker-entrypoint-initdb.d \
  -e MYSQL_ROOT_HOST=% \
  -e MYSQL_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" \
  -e MYSQL_DATABASE=${dbname} \
  -e MYSQL_USER=${dbuser} \
  -e MYSQL_PASSWORD=${dbpass} \
  -d mariadb:latest
sleep 10

# Step 2: Start ptvnc containers
echo -e "\e[32mStep 2. Start Packet Tracer VNC containers\e[0m"
mkdir -p "$(pwd)/shared"
chmod 777 "$(pwd)/shared"
for ((i=1; i<=$numofPT; i++)); do
    docker run -d \
      --name ptvnc$i --restart unless-stopped \
      --cpus=0.1 -m 1G --ulimit nproc=2048 --ulimit nofile=1024 \
      --dns=127.0.0.1 \
      -v "$(pwd)/${PTfile}:/PacketTracer.deb:ro" \
      -v pt_opt:/opt/pt \
      --mount type=bind,source="$(pwd)"/shared,target=/shared \
      -e PT_DEB_PATH=/PacketTracer.deb \
      ptvnc
    sleep $i
done

# Create desktop symlinks for easy access to /shared
echo -e "\e[32mCreating /shared symlinks and Packet Tracer shortcuts on Desktop\e[0m"
for ((i=1; i<=$numofPT; i++)); do
    docker exec ptvnc$i mkdir -p /home/ptuser/Desktop 2>/dev/null || true
    docker exec ptvnc$i ln -sf /shared /home/ptuser/Desktop/shared 2>/dev/null || true
    # Create Packet Tracer shortcut
    docker exec ptvnc$i bash -c "printf '%s\n' \
      '[Desktop Entry]' \
      'Version=1.0' \
      'Type=Application' \
      'Name=Packet Tracer' \
      'Comment=Cisco Packet Tracer Network Simulation Tool' \
      'Exec=/opt/pt/bin/PacketTracer' \
      'Icon=application-x-cisco-packet-tracer' \
      'StartupNotify=true' \
      'Terminal=false' \
      'Categories=Education;Science;Network;' \
      > /home/ptuser/Desktop/PacketTracer.desktop && chmod +x /home/ptuser/Desktop/PacketTracer.desktop" 2>/dev/null || true
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
mkdir -p "$(pwd)/shared"
chmod 777 "$(pwd)/shared"
docker run --restart always --name pt-nginx1 \
  --mount type=bind,source="$(pwd)"/ptweb-vnc/pt-nginx/www,target=/usr/share/nginx/html,readonly \
  --mount type=bind,source="$(pwd)"/ptweb-vnc/pt-nginx/conf,target=/etc/nginx/conf.d,readonly \
  --mount type=bind,source="$(pwd)"/shared,target=/shared,readonly \
  --link pt-guacamole:guacamole \
  -p 80:${nginxport} \
  -d nginx

# Step 6: Generate dynamic connections
echo -e "\e[32mStep 6. Generating dynamic Guacamole connections\e[0m"
sleep 10
bash generate-dynamic-connections.sh $numofPT
sleep 5

echo -e "\e[32m=== Deployment Complete ===\e[0m"
echo ""
echo "Services Status:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""
echo -e "\e[33m=== ACCESS INFORMATION ===\e[0m"
echo ""
if [[ "$ENABLE_HTTPS" == "true" ]]; then
    echo "Web Interface: https://localhost:$nginxport"
else
    echo "Web Interface: http://localhost:$nginxport"
fi
echo ""
echo "Guacamole Login:"
echo "  Username: ptadmin"
echo "  Password: $GUACAMOLE_PASSWORD"
echo ""
if [[ "$REQUIRE_DOWNLOAD_AUTH" == "true" ]]; then
    echo "Download Authentication:"
    echo "  Username: $DOWNLOAD_AUTH_USER"
    echo "  Password: $DOWNLOAD_AUTH_PASSWORD"
    echo ""
fi
echo "VNC Password (for direct VNC access):"
echo "  Password: $VNC_PASSWORD"
echo ""
echo "Database Credentials (saved in .env.secure):"
echo "  Root Password: $DB_ROOT_PASSWORD"
echo "  DB User: $dbuser"
echo "  DB Password: $dbpass"
echo ""
echo "Available Packet Tracer connections:"
for ((i=1; i<=$numofPT; i++)); do
    echo "  - pt$(printf "%02d" $i)"
done
echo ""
echo -e "\e[33m⚠️  IMPORTANT REMINDERS:\e[0m"
echo "  • All credentials are stored securely in .env.secure (mode 600)"
echo "  • Never commit .env.secure to git"
echo "  • For HTTPS: Add certificates to ptweb-vnc/certs/ and restart nginx"
if [[ "$ENABLE_GEOIP" == "true" ]]; then
    echo "  • GeoIP filtering is enabled: see GEOIP-SETUP.md for MaxMind setup"
fi
echo "  • Review SECURITY.md for production hardening checklist"
echo ""
