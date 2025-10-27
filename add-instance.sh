#!/bin/bash
# Add a new Packet Tracer instance without full redeployment
# Usage: bash add-instance.sh [instance_number]
# Example: bash add-instance.sh 4

set -e

PTfile="CiscoPacketTracer.deb"

# Get instance number from argument or calculate next
if [[ -n "$1" ]]; then
    instance_num=$1
else
    # Get highest instance number and add 1
    instance_num=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sed 's/ptvnc//' | sort -n | tail -1)
    instance_num=$((instance_num + 1))
fi

container_name="ptvnc$instance_num"

# Validate instance number
if [[ ! $instance_num =~ ^[0-9]+$ ]] || [[ $instance_num -lt 1 ]]; then
    echo "ERROR: Invalid instance number. Must be positive integer."
    exit 1
fi

echo -e "\e[32m=== Adding Packet Tracer Instance $instance_num ===\e[0m"

# Check if container already exists
if docker ps -a --format "table {{.Names}}" | grep -q "^${container_name}$"; then
    echo "ERROR: Container $container_name already exists!"
    exit 1
fi

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

# Step 1: Start new ptvnc container
echo -e "\e[32mStep 1. Starting container: $container_name\e[0m"
docker run -d \
  --name $container_name --restart unless-stopped \
  --cpus=0.1 -m 1G --ulimit nproc=2048 --ulimit nofile=1024 \
  --dns=127.0.0.1 \
  -v "$(pwd)/${PTfile}:/PacketTracer.deb:ro" \
  -v pt_opt:/opt/pt \
  -e PT_DEB_PATH=/PacketTracer.deb \
  ptvnc

sleep 10
echo "✅ Container started"

# Step 2: Get total number of instances
echo -e "\e[32mStep 2. Calculating total instances\e[0m"
total_instances=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | wc -l)
echo "Total instances now: $total_instances"

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
sleep 15

# Restart guacamole to pick up new links
echo "Restarting pt-guacamole..."
docker restart pt-guacamole
sleep 10

echo "✅ Services restarted"

# Step 4: Generate dynamic connections
echo -e "\e[32mStep 4. Generating dynamic Guacamole connections\e[0m"
bash generate-dynamic-connections.sh $total_instances
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
echo "Access at: http://localhost/guacamole/"
echo ""
