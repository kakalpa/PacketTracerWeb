#!/bin/bash
# Dynamic connection generator for Guacamole
# This script creates database entries that match the ACTUAL running ptvnc containers
# Usage: bash generate-dynamic-connections.sh
# (automatically detects running containers)
#
# NOTE: This script is now NON-DESTRUCTIVE. It:
# - Does NOT delete user-created connections (vnc-ptvnc*)
# - Does NOT delete bulk-created users
# - Only ensures the legacy pt01, pt02, etc. connections exist for ptadmin
# - New connections should be created via bulk-create API, not this script

set -e

dbuser="ptdbuser"
dbpass="ptdbpass"
dbname="guacamole_db"
mariadb_container="guacamole-mariadb"

# Get actual running ptvnc container numbers (not sequential count)
ptvnc_containers=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sed 's/ptvnc//' | sort -n)

if [[ -z "$ptvnc_containers" ]]; then
    echo "ERROR: No ptvnc containers found!"
    exit 1
fi

numofPT=$(echo "$ptvnc_containers" | wc -l)

echo "Generating legacy connections for $numofPT actual instances..."
echo "Found containers: $(echo $ptvnc_containers | tr '\n' ' ')"
echo ""
echo "⚠️  NOTE: This only creates legacy pt01, pt02... connections for backward compatibility"
echo "    For bulk-created users, connections are created automatically during user creation"
echo ""

# Create SQL file with dynamic connections (NON-DESTRUCTIVE)
cat > /tmp/dynamic_connections.sql << 'EOF'
USE guacamole_db;

-- Get ptadmin entity_id for permission assignment
SET @ptadmin_id = (SELECT entity_id FROM guacamole_entity WHERE name='ptadmin' AND type='USER');

EOF

# Get ptadmin entity_id
ptadmin_id=$(docker exec $mariadb_container mariadb -u${dbuser} -p${dbpass} ${dbname} -se "SELECT entity_id FROM guacamole_entity WHERE name='ptadmin' AND type='USER'")

echo "Admin entity ID: $ptadmin_id"

# Generate connection entries ONLY for legacy pt01, pt02, etc. naming
# Do NOT delete existing vnc-ptvnc* connections created by bulk-create
# NOTE: Using VNC protocol with guacd proxy (port 4822)
for instance_num in $ptvnc_containers; do
    connection_name="pt$(printf "%02d" $instance_num)"
    
    cat >> /tmp/dynamic_connections.sql << EOFCONN
-- Create legacy connection: $connection_name -> ptvnc$instance_num (VNC via guacd)
-- Only create if it doesn't already exist
INSERT IGNORE INTO \`guacamole_connection\` 
(\`connection_name\`, \`protocol\`, \`proxy_port\`, \`proxy_hostname\`, \`proxy_encryption_method\`, \`max_connections\`, \`max_connections_per_user\`, \`failover_only\`) 
VALUES ('$connection_name', 'vnc', 4822, 'pt-guacd', 'NONE', 1, 1, 0);

-- Grant access to ptadmin (only if not already granted)
INSERT IGNORE INTO \`guacamole_connection_permission\` 
(\`entity_id\`, \`connection_id\`, \`permission\`) 
VALUES (@ptadmin_id, (SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'READ');

-- Set connection parameters (only create if not already set)
INSERT IGNORE INTO \`guacamole_connection_parameter\` 
(\`connection_id\`, \`parameter_name\`, \`parameter_value\`) 
VALUES 
  ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'hostname', 'ptvnc$instance_num'),
  ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'port', '5901'),
  ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'username', 'ptuser'),
  ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'password', 'Cisco123');

EOFCONN
done

echo "SQL generated. Applying to database..."
docker exec -i $mariadb_container mariadb -u${dbuser} -p${dbpass} < /tmp/dynamic_connections.sql

echo "✅ Successfully ensured $numofPT legacy connections exist in Guacamole!"
echo ""
echo "Available legacy connections (for ptadmin):"
for instance_num in $ptvnc_containers; do
    echo "  - pt$(printf "%02d" $instance_num)"
done
echo ""
echo "User-specific connections (vnc-ptvnc*) are created automatically during bulk user creation."

# Clean up
rm /tmp/dynamic_connections.sql
