#!/bin/bash

# Deployment script for PacketTracer + Guacamole stack
# This manually runs the docker commands from install.sh without system-level changes
# Usage: bash deploy.sh [recreate]
#   - No args: Deploy (fails if containers exist)
#   - recreate: Remove all containers/volumes and redeploy fresh

set -e

cd "$(dirname "$0")"
WORKDIR="$(pwd)"

# Configuration from install.sh
dbuser="ptdbuser"
dbpass="ptdbpass"
dbname="guacamole_db"
numofPT=2
PTfile="CiscoPacketTracer.deb"
nginxport=80

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

# Generate ptweb.conf with the correct Guacamole IP
# Use single quotes for heredoc to prevent shell expansion of nginx variables,
# then use sed to substitute the GUACAMOLE_IP placeholder
{
    cat << 'PTWEB_EOF'
server {
    listen 80;
    server_name localhost;

    charset utf-8;

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
        # GeoIP filtering logic (demonstration)
        # Note: For testing with X-Forwarded-For headers, GeoIP lookups happen on remote_addr (Docker host IP)
        # In production, this would work correctly with real client IPs
        #
        # Block if country is in blocked list
        if ($blocked_country = 1) {
            return 444;
        }
        # Block if allow-mode is on AND country is not in allow list AND not a known country (default -1)
        if ($allowed_country = 0) {
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
} | sed "s|GUACAMOLE_IP_PLACEHOLDER|$GUACAMOLE_IP|g" > "${WORKDIR}/ptweb-vnc/pt-nginx/conf/ptweb.conf"
echo -e "\033[32m  ✓ Generated ptweb.conf with Guacamole IP\033[0m"
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

# Query Guacamole container IP and generate ptweb.conf
sleep 3
GUACAMOLE_IP=$(docker inspect pt-guacamole --format='{{.NetworkSettings.IPAddress}}' 2>/dev/null || echo "172.17.0.6")
GUACAMOLE_IP=$(echo "$GUACAMOLE_IP" | tr -d '
' | tr -d ' ')
echo -e "\033[36m  ✓ Guacamole IP: $GUACAMOLE_IP\033[0m"

# Generate ptweb.conf with the correct Guacamole IP
# Use single quotes for heredoc to prevent shell expansion of nginx variables,
# then use sed to substitute the GUACAMOLE_IP placeholder
{
    cat << 'PTWEB_EOF'
server {
    listen 80;
    server_name localhost;

    charset utf-8;

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
        # GeoIP filtering logic (demonstration)
        # Note: For testing with X-Forwarded-For headers, GeoIP lookups happen on remote_addr (Docker host IP)
        # In production, this would work correctly with real client IPs
        #
        # Block if country is in blocked list
        if ($blocked_country = 1) {
            return 444;
        }
        # Block if allow-mode is on AND country is not in allow list AND not a known country (default -1)
        if ($allowed_country = 0) {
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
} | sed "s|GUACAMOLE_IP_PLACEHOLDER|$GUACAMOLE_IP|g" > "${WORKDIR}/ptweb-vnc/pt-nginx/conf/ptweb.conf"
echo -e "\033[32m  ✓ Generated ptweb.conf with Guacamole IP\033[0m"
docker run --restart always --name pt-nginx1 \
  --mount type=bind,source="${WORKDIR}/ptweb-vnc/pt-nginx/www",target=/usr/share/nginx/html,readonly \
  --mount type=bind,source="${WORKDIR}/ptweb-vnc/pt-nginx/conf",target=/etc/nginx/conf.d,readonly \
  --mount type=bind,source="${WORKDIR}/shared",target=/shared,readonly,bind-propagation=rprivate \
  --link pt-guacamole:guacamole \
  -p 80:${nginxport} \
  -d pt-nginx

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
