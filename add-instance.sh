#!/bin/bash
# Add new Packet Tracer instances without full redeployment
# Usage: bash add-instance.sh [count]
# Example: bash add-instance.sh 1   # Add 1 more instance
# Example: bash add-instance.sh 3   # Add 3 more instances
# If no argument, adds 1 instance

set -e

PTfile="CiscoPacketTracer.deb"
WORKDIR="$(cd "$(dirname "$0")" && pwd)"

# Load environment configuration from .env if it exists
if [ -f "$WORKDIR/.env" ]; then
    source "$WORKDIR/.env"
fi

# SSL/HTTPS Configuration (from .env or defaults)
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/ssl/certs/server.crt}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/ssl/private/server.key}

# Check if ptvnc image exists, build if not
if ! docker image inspect ptvnc:latest &>/dev/null; then
    echo "Building ptvnc image..."
    docker build -t ptvnc "${WORKDIR}/ptweb-vnc/"
fi

# Get number of instances to add (default: 1)
instances_to_add=${1:-1}

# Validate count
if [[ ! $instances_to_add =~ ^[0-9]+$ ]] || [[ $instances_to_add -lt 1 ]]; then
    echo "ERROR: Invalid count. Must be positive integer."
    exit 1
fi

# Get current highest instance number
current_max=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sed 's/ptvnc//' | sort -n | tail -1)
if [[ -z "$current_max" ]]; then
    current_max=0
fi

echo -e "\e[32m=== Adding $instances_to_add Packet Tracer Instance(s) ===\e[0m"
echo "Current max instance: ptvnc$current_max"
echo "Will create: ptvnc$((current_max+1)) to ptvnc$((current_max+instances_to_add))"
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
echo ""

# Prepare shared directory
mkdir -p "$(pwd)/shared"
chmod 777 "$(pwd)/shared"

# Step 1: Start new ptvnc containers
echo -e "\e[32mStep 1. Starting $instances_to_add new container(s)\e[0m"

for ((i=0; i<instances_to_add; i++)); do
    instance_num=$((current_max + i + 1))
    container_name="ptvnc$instance_num"
    
    # Check if container already exists
    if docker ps -a --format "table {{.Names}}" | grep -q "^${container_name}$"; then
        echo "⚠️  Container $container_name already exists, skipping..."
        continue
    fi
    
    echo "Creating $container_name..."
    docker run -d \
      --name $container_name --restart unless-stopped \
      --cpus=0.1 -m 1G --ulimit nproc=2048 --ulimit nofile=1024 \
      --dns=127.0.0.1 \
      -v "${WORKDIR}/${PTfile}:/PacketTracer.deb:ro" \
      -v pt_opt:/opt/pt \
      --mount type=bind,source="${WORKDIR}/shared",target=/shared,bind-propagation=rprivate \
      -e PT_DEB_PATH=/PacketTracer.deb \
      ptvnc
    
    sleep 2
done

echo "✅ Containers started"
echo ""

# Create desktop symlinks for new instances
echo -e "\e[32mStep 1b. Creating /shared symlinks on Desktop\e[0m"
for ((i=0; i<instances_to_add; i++)); do
    instance_num=$((current_max + i + 1))
    container_name="ptvnc$instance_num"
    
    if docker ps --format "table {{.Names}}" | grep -q "^${container_name}$"; then
        docker exec $container_name mkdir -p /home/ptuser/Desktop 2>/dev/null || true
        docker exec $container_name ln -sf /shared /home/ptuser/Desktop/shared 2>/dev/null || true
    fi
done
sleep 2

# Step 2: Get total number of instances
echo -e "\e[32mStep 2. Calculating total instances\e[0m"
total_instances=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | wc -l)
echo "Total instances now: $total_instances"
echo ""

# Step 3: Restart guacamole services with updated links
echo -e "\e[32mStep 3. Restarting Guacamole services with updated links\e[0m"

# Stop and remove old guacd
echo "Stopping pt-guacd..."
docker stop pt-guacd 2>/dev/null || true
docker rm pt-guacd 2>/dev/null || true

# Build link string
linkstr=""
for ((i=1; i<=$total_instances; i++)); do
    if docker ps --format "table {{.Names}}" | grep -q "^ptvnc$i$"; then
        linkstr="${linkstr} --link ptvnc$i:ptvnc$i"
    fi
done

# Start new guacd with all links
docker run --name pt-guacd --restart always -d ${linkstr} guacamole/guacd
sleep 20

# Recreate guacamole to pick up new links
echo "Recreating pt-guacamole..."
docker stop pt-guacamole 2>/dev/null || true
docker rm pt-guacamole 2>/dev/null || true
sleep 5
docker run --name pt-guacamole --restart always \
  --link pt-guacd:guacd \
  --link guacamole-mariadb:mysql \
  -e MYSQL_DATABASE=guacamole_db \
  -e MYSQL_USER=ptdbuser \
  -e MYSQL_PASSWORD=ptdbpass \
  -d guacamole/guacamole
sleep 10

# Recreate nginx to re-link to guacamole
echo "Recreating pt-nginx1..."
docker stop pt-nginx1 2>/dev/null || true
docker rm pt-nginx1 2>/dev/null || true
sleep 3

# Mount SSL certificates if HTTPS is enabled
SSL_MOUNTS=""
if [ "$ENABLE_HTTPS" = "true" ]; then
    if [ -f "$WORKDIR/ssl/server.crt" ]; then
        SSL_MOUNTS="$SSL_MOUNTS --mount type=bind,source=\"$WORKDIR/ssl/server.crt\",target=$SSL_CERT_PATH,readonly"
    fi
    if [ -f "$WORKDIR/ssl/server.key" ]; then
        SSL_MOUNTS="$SSL_MOUNTS --mount type=bind,source=\"$WORKDIR/ssl/server.key\",target=$SSL_KEY_PATH,readonly"
    fi
fi

eval "docker run --restart always --name pt-nginx1 \
  --mount type=bind,source=\"${WORKDIR}/ptweb-vnc/pt-nginx/www\",target=/usr/share/nginx/html,readonly \
  --mount type=bind,source=\"${WORKDIR}/ptweb-vnc/pt-nginx/conf\",target=/etc/nginx/conf.d,readonly \
  --mount type=bind,source=\"${WORKDIR}/shared\",target=/shared,readonly,bind-propagation=rprivate \
  $SSL_MOUNTS \
  --link pt-guacamole:guacamole \
  -p 80:80 \
  $([ "$ENABLE_HTTPS" = "true" ] && echo "-p 443:443") \
  -d pt-nginx"
sleep 5

echo "✅ Services restarted"

# Step 4: Generate dynamic connections
echo -e "\e[32mStep 4. Generating dynamic Guacamole connections\e[0m"
bash generate-dynamic-connections.sh
sleep 5

echo ""
echo -e "\e[32m=== Instance Added Successfully ===\e[0m"
echo ""
echo "Services Status:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "pt-nginx1|pt-guacamole|ptvnc|guacamole-mariadb|pt-guacd"
echo ""
echo "Available Packet Tracer connections:"
for ((i=1; i<=$total_instances; i++)); do
    if docker ps --format "table {{.Names}}" | grep -q "^ptvnc$i$"; then
        echo "  - pt$(printf "%02d" $i)"
    fi
done
echo ""
echo "Access at: http://localhost/"
echo ""
