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
WORKDIR="$(cd "$(dirname "$0")" && pwd)"

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

# Load environment configuration from .env safely if it exists
if [ -f "$WORKDIR/.env" ]; then
    load_env_file "$WORKDIR/.env"
fi

# SSL/HTTPS & GeoIP Configuration (from .env or defaults)
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/ssl/ptweb/server.crt}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/ssl/ptweb/server.key}
NGINX_GEOIP_ALLOW=${NGINX_GEOIP_ALLOW:-false}
NGINX_GEOIP_BLOCK=${NGINX_GEOIP_BLOCK:-false}

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
    
    # Archive and clean instance storage directory
    INSTANCE_DIR="${WORKDIR}/shared/instances/${container_name}"
    ARCHIVE_DIR="${WORKDIR}/shared/archive"
    if [ -d "$INSTANCE_DIR" ]; then
        mkdir -p "$ARCHIVE_DIR"
        ARCHIVE_FILE="${ARCHIVE_DIR}/${container_name}_$(date +%Y%m%d_%H%M%S).tar.gz"
        echo "Archiving storage for $container_name to $ARCHIVE_FILE..."
        tar -czf "$ARCHIVE_FILE" -C "${WORKDIR}/shared/instances" "$container_name" 2>/dev/null || true
        rm -rf "$INSTANCE_DIR"
        echo "  ✓ Cleaned storage for $container_name"
    fi

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

# Ensure ptnet network exists
docker network create ptnet 2>/dev/null || true

# Stop and remove old guacd
echo "Stopping pt-guacd..."
docker stop pt-guacd 2>/dev/null || true
docker rm pt-guacd 2>/dev/null || true

# Start new guacd on ptnet (no legacy --link)
docker run --name pt-guacd --restart always \
  --network ptnet \
  -d guacamole/guacd:latest
sleep 20

# Recreate guacamole on ptnet
echo "Recreating pt-guacamole..."
docker stop pt-guacamole 2>/dev/null || true
docker rm pt-guacamole 2>/dev/null || true
sleep 5
docker run --name pt-guacamole --restart always \
  --network ptnet \
  -e MYSQL_HOSTNAME=guacamole-mariadb \
  -e MYSQL_DATABASE=guacamole_db \
  -e MYSQL_USER=ptdbuser \
  -e MYSQL_PASSWORD=ptdbpass \
  -e GUACAMOLE_GUACD_HOSTNAME=pt-guacd \
  -e GUACAMOLE_GUACD_PORT=4822 \
  -d guacamole/guacamole
sleep 10

# Recreate nginx
echo "Recreating pt-nginx1..."
docker stop pt-nginx1 2>/dev/null || true
docker rm pt-nginx1 2>/dev/null || true
sleep 3

# Ensure host SSL and Certbot directories exist
mkdir -p "${WORKDIR}/ssl" \
         "${WORKDIR}/certbot/conf" \
         "${WORKDIR}/certbot/www/.well-known/acme-challenge"

if [ "$ENABLE_HTTPS" = "true" ] || [ "$ENABLE_HTTPS" = "1" ]; then
    bash "${WORKDIR}/generate-ssl-cert.sh" --if-missing
fi

# Mount GeoIP database if GeoIP filtering is enabled
GEOIP_ARGS=()
if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_ALLOW" = "1" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; then
    GEOIP_FILE="${WORKDIR}/geoip/GeoIP.dat"
    if [ -f "$GEOIP_FILE" ]; then
        GEOIP_ARGS+=(--mount "type=bind,source=${GEOIP_FILE},target=/usr/share/GeoIP/GeoIP.dat,readonly")
    fi
fi

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

# Reconnect recreated containers to pt-stack if pt-stack exists
if docker network inspect pt-stack &>/dev/null; then
    for c in pt-guacd pt-guacamole pt-nginx1; do
        docker network connect pt-stack "$c" 2>/dev/null || true
    done
fi
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
