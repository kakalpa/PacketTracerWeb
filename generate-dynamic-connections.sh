#!/bin/bash
# Dynamic connection generator for Guacamole
# This script creates database entries that match the number of running ptvnc containers
# Usage: bash generate-dynamic-connections.sh [num_instances]

set -e

dbuser="ptdbuser"
dbpass="ptdbpass"
dbname="guacamole_db"
mariadb_container="guacamole-mariadb"

# Get number of instances from argument or count running containers
if [[ -n "$1" ]]; then
    numofPT=$1
else
    numofPT=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | wc -l || echo 2)
fi

echo "Generating connections for $numofPT instances..."

# Create SQL file with dynamic connections
cat > /tmp/dynamic_connections.sql << 'EOF'
USE guacamole_db;

-- Clear existing connections and related data
DELETE FROM guacamole_connection_permission;
DELETE FROM guacamole_connection_parameter;
DELETE FROM guacamole_connection;
DELETE FROM guacamole_connection_group;

-- Reset auto_increment for connection table
ALTER TABLE guacamole_connection AUTO_INCREMENT = 1;

-- Clear existing users/entities (except ptadmin)
DELETE FROM guacamole_user_permission WHERE affected_user_id NOT IN (SELECT user_id FROM guacamole_user WHERE entity_id = (SELECT entity_id FROM guacamole_entity WHERE name = 'ptadmin'));
DELETE FROM guacamole_user_group_member;
DELETE FROM guacamole_user WHERE entity_id NOT IN (SELECT entity_id FROM guacamole_entity WHERE name = 'ptadmin');
DELETE FROM guacamole_user_group WHERE entity_id NOT IN (SELECT entity_id FROM guacamole_entity WHERE name = 'admins' OR name = 'PTuser');
DELETE FROM guacamole_entity WHERE name NOT IN ('ptadmin', 'admins', 'PTuser');

-- Reset auto_increment for entity table  
ALTER TABLE guacamole_entity AUTO_INCREMENT = 5;

EOF

# Get ptadmin entity_id
ptadmin_id=$(docker exec $mariadb_container mariadb -u${dbuser} -p${dbpass} ${dbname} -se "SELECT entity_id FROM guacamole_entity WHERE name='ptadmin' AND type='USER'")

echo "Admin entity ID: $ptadmin_id"

# Generate connection entries dynamically
for ((i=1; i<=$numofPT; i++)); do
    connection_name="pt$(printf "%02d" $i)"
    
    cat >> /tmp/dynamic_connections.sql << EOFCONN
-- Connection: $connection_name
INSERT INTO \`guacamole_entity\` (\`name\`, \`type\`) VALUES ('$connection_name', 'USER');

SET @conn_id = (SELECT LAST_INSERT_ID());

INSERT INTO \`guacamole_connection\` (\`connection_name\`, \`protocol\`, \`proxy_port\`, \`proxy_hostname\`, \`proxy_encryption_method\`, \`max_connections\`, \`max_connections_per_user\`, \`failover_only\`) 
VALUES ('$connection_name', 'vnc', 4822, 'guacd', 'NONE', 1, 1, 0);

SET @last_conn = (SELECT LAST_INSERT_ID());

INSERT INTO \`guacamole_connection_parameter\` (\`connection_id\`, \`parameter_name\`, \`parameter_value\`) 
VALUES 
  (@last_conn, 'hostname', 'ptvnc$i'),
  (@last_conn, 'port', '5901'),
  (@last_conn, 'password', 'Cisco123');

-- Grant access to ptadmin
INSERT INTO \`guacamole_connection_permission\` (\`entity_id\`, \`connection_id\`, \`permission\`) 
VALUES ($ptadmin_id, @last_conn, 'READ');

EOFCONN
done

echo "SQL generated. Applying to database..."
docker exec -i $mariadb_container mariadb -u${dbuser} -p${dbpass} < /tmp/dynamic_connections.sql

echo "✅ Successfully created $numofPT dynamic connections in Guacamole!"
echo ""
echo "Available connections:"
for ((i=1; i<=$numofPT; i++)); do
    echo "  - pt$(printf "%02d" $i)"
done

# Clean up
rm /tmp/dynamic_connections.sql
