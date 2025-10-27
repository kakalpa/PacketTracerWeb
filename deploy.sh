#!/bin/bash

# Deployment script for PacketTracer + Guacamole stack
# This manually runs the docker commands from install.sh without system-level changes

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
mkdir -p "${WORKDIR}/shared"
chmod 777 "${WORKDIR}/shared"
docker run --restart always --name pt-nginx1 \
  --mount type=bind,source="${WORKDIR}/ptweb-vnc/pt-nginx/www",target=/usr/share/nginx/html,readonly \
  --mount type=bind,source="${WORKDIR}/ptweb-vnc/pt-nginx/conf",target=/etc/nginx/conf.d,readonly \
  --mount type=bind,source="${WORKDIR}/shared",target=/shared,readonly,bind-propagation=rprivate \
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
echo "Access the web interface at: http://localhost"
echo ""
echo "Available Packet Tracer connections:"
for ((i=1; i<=$numofPT; i++)); do
    echo "  - pt$(printf "%02d" $i)"
done
echo ""
