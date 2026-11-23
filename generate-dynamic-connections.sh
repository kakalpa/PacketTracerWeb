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

# Create SQL file with dynamic connections (NON-DESTRUCTIVE & DEDUPLICATING)
cat > /tmp/dynamic_connections.sql << 'EOF'
USE guacamole_db;

-- Deduplicate any legacy connections if duplicates already exist (keep lowest connection_id)
DELETE c1 FROM `guacamole_connection` c1
INNER JOIN `guacamole_connection` c2 
WHERE c1.connection_name = c2.connection_name AND c1.connection_id > c2.connection_id;

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
    vnc_pass=$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "ptvnc$instance_num" 2>/dev/null | awk -F= '$1=="VNC_PASS"{print $2; exit}' | tr -dc 'A-Za-z0-9' || true)
    vnc_pass=${vnc_pass:-Cisco123}
    
    cat >> /tmp/dynamic_connections.sql << EOFCONN
-- Create legacy connection: $connection_name -> ptvnc$instance_num (VNC via guacd)
-- Only create if it doesn't already exist (avoid NULL parent_id unique constraint duplicate bug)
INSERT INTO \`guacamole_connection\` 
(\`connection_name\`, \`protocol\`, \`proxy_port\`, \`proxy_hostname\`, \`proxy_encryption_method\`, \`max_connections\`, \`max_connections_per_user\`, \`failover_only\`) 
SELECT '$connection_name', 'vnc', 4822, 'pt-guacd', 'NONE', NULL, NULL, 0
WHERE NOT EXISTS (
    SELECT 1 FROM \`guacamole_connection\` WHERE \`connection_name\` = '$connection_name'
);

-- Grant access to ptadmin (only if not already granted)
INSERT IGNORE INTO \`guacamole_connection_permission\` 
(\`entity_id\`, \`connection_id\`, \`permission\`) 
SELECT @ptadmin_id, connection_id, 'READ'
FROM \`guacamole_connection\`
WHERE connection_name = '$connection_name'
AND @ptadmin_id IS NOT NULL;

-- Set connection parameters idempotently
INSERT INTO \`guacamole_connection_parameter\` (\`connection_id\`, \`parameter_name\`, \`parameter_value\`)
SELECT c.connection_id, 'hostname', 'ptvnc$instance_num' FROM \`guacamole_connection\` c WHERE c.connection_name = '$connection_name'
ON DUPLICATE KEY UPDATE \`parameter_value\` = VALUES(\`parameter_value\`);

INSERT INTO \`guacamole_connection_parameter\` (\`connection_id\`, \`parameter_name\`, \`parameter_value\`)
SELECT c.connection_id, 'port', '5901' FROM \`guacamole_connection\` c WHERE c.connection_name = '$connection_name'
ON DUPLICATE KEY UPDATE \`parameter_value\` = VALUES(\`parameter_value\`);

INSERT INTO \`guacamole_connection_parameter\` (\`connection_id\`, \`parameter_name\`, \`parameter_value\`)
SELECT c.connection_id, 'username', 'ptuser' FROM \`guacamole_connection\` c WHERE c.connection_name = '$connection_name'
ON DUPLICATE KEY UPDATE \`parameter_value\` = VALUES(\`parameter_value\`);

INSERT INTO \`guacamole_connection_parameter\` (\`connection_id\`, \`parameter_name\`, \`parameter_value\`)
SELECT c.connection_id, 'password', '$vnc_pass' FROM \`guacamole_connection\` c WHERE c.connection_name = '$connection_name'
ON DUPLICATE KEY UPDATE \`parameter_value\` = VALUES(\`parameter_value\`);

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
