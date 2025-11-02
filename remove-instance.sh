#!/bin/bash
# Remove Packet Tracer instances without full redeployment
# Usage: bash remove-instance.sh [count | instance_names]
# Examples:
#   bash remove-instance.sh                  # Remove 1 instance (highest numbered)
#   bash remove-instance.sh 2                # Remove 2 instances (highest numbered)
#   bash remove-instance.sh pt02             # Remove specific instance pt02
#   bash remove-instance.sh pt02 pt03        # Remove multiple specific instances
#   bash remove-instance.sh 1 pt02 pt03      # Remove 1 + pt02 + pt03

PTfile="CiscoPacketTracer.deb"

# Parse arguments - check if they are instance names (pt01, pt02) or count
instances_to_remove_list=""
instances_to_remove_count=1  # default: remove 1 instance

if [[ $# -gt 0 ]]; then
    # Check first argument
    if [[ $1 =~ ^pt[0-9]{2}$ ]]; then
        # Argument is instance name (pt01, pt02, etc.)
        instances_to_remove_list="$@"
    elif [[ $1 =~ ^[0-9]+$ ]] && [[ $1 -gt 0 ]]; then
        # Argument is count
        instances_to_remove_count=$1
    else
        echo "ERROR: Invalid argument '$1'"
        echo "Usage:"
        echo "  bash remove-instance.sh               # Remove 1 instance"
        echo "  bash remove-instance.sh 2             # Remove 2 instances"
        echo "  bash remove-instance.sh pt02          # Remove specific instance"
        echo "  bash remove-instance.sh pt02 pt03     # Remove multiple instances"
        exit 1
    fi
fi

echo -e "\e[32m╔═══════════════════════════════════════════════╗\e[0m"
echo -e "\e[32m║  Removing Packet Tracer Instance(s)          ║\e[0m"
echo -e "\e[32m╚═══════════════════════════════════════════════╝\e[0m"
echo ""

# Get current instances and sort
current_instances=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sed 's/ptvnc//' | sort -n)

if [[ -z "$current_instances" ]]; then
    echo "ERROR: No ptvnc instances found!"
    exit 1
fi

# Count current instances
total_current=$(echo "$current_instances" | wc -l)

# Determine which instances to remove
if [[ -z "$instances_to_remove_list" ]]; then
    # Remove by count (highest numbers first)
    if [[ $instances_to_remove_count -gt $total_current ]]; then
        echo "ERROR: Only $total_current instances exist. Cannot remove $instances_to_remove_count."
        exit 1
    fi
    instances_to_remove_list=$(echo "$current_instances" | tail -n $instances_to_remove_count | tac)
    remaining_count=$((total_current - instances_to_remove_count))
    remove_mode="count"
else
    # Remove by specific instance names
    remove_mode="specific"
    remaining_count=$total_current
    
    # Validate that specified instances exist
    for instance_name in $instances_to_remove_list; do
        # Extract instance number from name (pt02 -> 02 -> 2)
        instance_num=$(echo "$instance_name" | sed 's/pt0*//')
        
        if ! echo "$current_instances" | grep -q "^$instance_num$"; then
            echo "ERROR: Instance $instance_name (ptvnc$instance_num) does not exist!"
            exit 1
        fi
        ((remaining_count--))
    done
    
    # Convert instance names to numbers for consistency
    instances_to_remove_nums=""
    for instance_name in $instances_to_remove_list; do
        instance_num=$(echo "$instance_name" | sed 's/pt0*//')
        instances_to_remove_nums="$instances_to_remove_nums $instance_num"
    done
    instances_to_remove_list=$instances_to_remove_nums
fi

echo -e "\e[33mCurrent instances: $total_current\e[0m"
echo -e "\e[33mInstances to remove: $(echo "$instances_to_remove_list" | wc -w)\e[0m"
echo -e "\e[33mRemaining instances: $remaining_count\e[0m"
echo ""
echo "Instances to be removed:"
for instance_num in $instances_to_remove_list; do
    echo "  - ptvnc$instance_num (pt$(printf "%02d" $instance_num))"
done
echo ""

# Ask for confirmation
read -p "Are you sure? (yes/no): " confirmation
if [[ "$confirmation" != "yes" ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo -e "\e[32m=== Starting removal process ===\e[0m"
echo ""

# Step 1: Stop and remove ptvnc containers
echo -e "\e[32mStep 1. Stopping and removing containers\e[0m"
for instance_num in $instances_to_remove_list; do
    container_name="ptvnc$instance_num"
    echo "Removing $container_name..."
    docker stop $container_name 2>/dev/null || true
    docker rm $container_name 2>/dev/null || true
done
sleep 2
echo "✅ Containers removed"
echo ""

# Step 2: Calculate remaining instances
echo -e "\e[32mStep 2. Calculating remaining instances\e[0m"
total_instances=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | wc -l)

if [ $total_instances -eq 0 ]; then
    echo "⚠️  All instances removed. Skipping Guacamole updates."
    echo "To redeploy, run: bash deploy.sh"
    exit 0
fi

echo "Remaining instances: $total_instances"
echo ""

# Step 3: Restart guacamole services
echo -e "\e[32mStep 3. Restarting Guacamole services\e[0m"

# Stop and remove old guacd
echo "Stopping pt-guacd..."
docker stop pt-guacd 2>/dev/null || true
docker rm pt-guacd 2>/dev/null || true

# Build link string for remaining instances
linkstr=""
remaining_instances=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sed 's/ptvnc//' | sort -n)
for instance_num in $remaining_instances; do
    linkstr="${linkstr} --link ptvnc$instance_num:ptvnc$instance_num"
done

# Start new guacd with remaining links
docker run --name pt-guacd --restart always -d ${linkstr} guacamole/guacd
sleep 20

# Recreate guacamole
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

# Recreate nginx
echo "Recreating pt-nginx1..."
docker stop pt-nginx1 2>/dev/null || true
docker rm pt-nginx1 2>/dev/null || true
sleep 3
docker run --restart always --name pt-nginx1 \
  --mount type=bind,source="$(pwd)"/ptweb-vnc/pt-nginx/www,target=/usr/share/nginx/html,readonly \
  --mount type=bind,source="$(pwd)"/ptweb-vnc/pt-nginx/conf,target=/etc/nginx/conf.d,readonly \
  --mount type=bind,source="$(pwd)"/shared,target=/shared,readonly \
  --link pt-guacamole:guacamole \
  -p 80:80 \
  -d pt-nginx
sleep 5

echo "✅ Services restarted"
echo ""

# Step 4: Generate dynamic connections
echo -e "\e[32mStep 4. Regenerating Guacamole connections\e[0m"
bash generate-dynamic-connections.sh
sleep 5

echo ""
echo -e "\e[32m=== Instance(s) Removed Successfully ===\e[0m"
echo ""
echo "Services Status:"
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" | grep -E "pt-nginx1|pt-guacamole|ptvnc|guacamole-mariadb|pt-guacd"
echo ""
echo "Available Packet Tracer connections:"
docker ps --format "table {{.Names}}" | grep "^ptvnc" | sed 's/ptvnc/  - pt/' | sed 's/pt\([0-9]\)$/pt0\1/' | sed 's/pt0\([0-9][0-9]\)$/pt\1/'
echo ""
echo "Access at: http://localhost/"
echo ""

# Warning about user impact
echo -e "\e[33m⚠️  WARNING:\e[0m"
echo "Active users were disconnected during the removal process."
echo "They need to refresh their browser and reconnect."
echo ""
