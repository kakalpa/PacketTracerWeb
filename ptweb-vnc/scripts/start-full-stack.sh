#!/usr/bin/env bash
set -euo pipefail

# Helper to bring up the full stack: MariaDB, guacd, guacamole, nginx, and N PacketTracer containers
# Usage: ./ptweb-vnc/scripts/start-full-stack.sh [num_of_pt]

NUM=${1:-10}
IMAGE_NAME=${IMAGE_NAME:-ptvnc}
PT_CONTAINER_BASE=${PT_CONTAINER_BASE:-ptvnc}
DB_USER=${DB_USER:-ptdbuser}
DB_PASS=${DB_PASS:-ptdbpass}
DB_NAME=${DB_NAME:-guacamole_db}

echo "Building Packet Tracer image (this uses the repo Dockerfile)..."
docker build -t ${IMAGE_NAME} .

echo "Starting core services with docker-compose..."
docker-compose up -d mariadb guacd guacamole nginx

echo "Waiting for MariaDB to initialize..."
sleep 10

# Import DB dump
if docker ps --filter "name=guacamole-mariadb" --format '{{.Names}}' | grep -q guacamole-mariadb; then
  echo "Importing DB dump into MariaDB container..."
  docker exec -i guacamole-mariadb mysql -u${DB_USER} -p${DB_PASS} ${DB_NAME} < db-dump.sql || echo "DB import may have already been applied"
else
  echo "MariaDB container not found; skipping DB import"
fi

# Start Packet Tracer containers
echo "Starting ${NUM} Packet Tracer containers..."
for i in $(seq 1 ${NUM}); do
  cname=${PT_CONTAINER_BASE}${i}
  echo "Starting container ${cname}"
  docker run -d --name ${cname} --restart unless-stopped --cpus=0.5 -m 2G --kernel-memory 128M --oom-kill-disable --ulimit nproc=2048 --ulimit nofile=1024:1024 ${IMAGE_NAME} || echo "Failed to start ${cname} (may already exist)"
  sleep 1
  
  # Connect container to pt-stack network for Guacamole access
  docker network connect pt-stack ${cname} 2>/dev/null || true
  
  # Create Desktop symlink to /shared for easy file access
  docker exec ${cname} mkdir -p /home/ptuser/Desktop 2>/dev/null || true
  docker exec ${cname} ln -sf /shared /home/ptuser/Desktop/shared 2>/dev/null || true
done

echo "All done. Access Guacamole via http://<host>/guacamole (nginx proxies to guacamole)."
echo "You may need to wait a minute for the services to fully start."
