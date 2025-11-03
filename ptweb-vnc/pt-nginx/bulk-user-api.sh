#!/bin/bash
# Bulk User & Instance Management API
# This script handles user creation and deployment

set -euo pipefail

# Configuration
DB_HOST="mariadb"
DB_USER="ptdbuser"
DB_PASS="ptdbpass"
DB_NAME="guacamole_db"
ADMIN_USER="admin"
ADMIN_PASS="admin123"

# Temporary directory for uploads
UPLOAD_DIR="/tmp/bulk-user-uploads"
mkdir -p "$UPLOAD_DIR"

# Log file
LOG_FILE="/tmp/bulk-user-api.log"

# Helper function to log
log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Helper function to return JSON response
json_response() {
    local success=$1
    local message=$2
    local action=${3:-""}
    local data=${4:-""}
    
    echo -n "Content-Type: application/json\r\n\r\n"
    
    if [ -z "$data" ]; then
        python3 -c "import json; print(json.dumps({'success': $success, 'message': '''$message''', 'action': '''$action'''}))"
    else
        python3 -c "import json; print(json.dumps({'success': $success, 'message': '''$message''', 'action': '''$action''', 'results': json.loads('''$data''')}))"
    fi
}

# Parse POST data and CSV
parse_request() {
    local temp_file=$(mktemp)
    cat > "$temp_file"
    
    # Extract CSV data (basic parsing)
    # This is a simplified version - in production use a proper form parser
    
    echo "$temp_file"
}

# Create user in Guacamole database
create_guacamole_user() {
    local username=$1
    local password=$2
    
    # Generate salt and hash
    local salt=$(python3 -c "import os; import binascii; print(binascii.hexlify(os.urandom(16)).decode())")
    local hash=$(python3 -c "import hashlib; import binascii; salt=binascii.unhexlify('$salt'); pwd='$password'.encode(); h=hashlib.sha256(pwd+salt).digest(); print(binascii.hexlify(h).decode())")
    
    log "Creating user: $username"
    
    # Check if user exists
    local exists=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -e "SELECT COUNT(*) FROM guacamole_entity WHERE name = '$username'" 2>/dev/null || echo "0")
    
    if [ "$exists" -gt 0 ]; then
        log "User $username already exists"
        echo '{"success": true, "message": "User already exists"}'
        return
    fi
    
    # Insert user
    mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
        INSERT INTO guacamole_entity (name, type) VALUES ('$username', 'USER');
        INSERT INTO guacamole_user (entity_id, password_hash, password_salt) 
        SELECT entity_id, UNHEX('$hash'), UNHEX('$salt') FROM guacamole_entity WHERE name = '$username';
    " 2>/dev/null
    
    log "User $username created successfully"
    echo '{"success": true, "message": "User created"}'
}

# Deploy instance for user
deploy_instance() {
    local username=$1
    local workdir=$2
    
    log "Deploying instance for: $username"
    
    cd "$workdir"
    local output=$(bash ./add-instance.sh 1 2>&1 || true)
    
    # Parse instance number
    local instance_num=$(echo "$output" | grep -oP 'Creating ptvnc\K\d+' | head -1 || echo "")
    
    if [ -z "$instance_num" ]; then
        log "Failed to deploy instance for $username"
        echo "{\"success\": false, \"message\": \"Failed to deploy instance\"}"
        return 1
    fi
    
    log "Instance ptvnc$instance_num created for $username"
    
    # Register connections
    bash ./generate-dynamic-connections.sh 2>&1 || true
    
    # Assign connection to user
    local conn_name="pt$(printf '%02d' $instance_num)"
    local user_id=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -e "SELECT entity_id FROM guacamole_entity WHERE name = '$username'" 2>/dev/null || echo "")
    local conn_id=$(mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -N -e "SELECT connection_id FROM guacamole_connection WHERE connection_name = '$conn_name'" 2>/dev/null || echo "")
    
    if [ -n "$user_id" ] && [ -n "$conn_id" ]; then
        mysql -h "$DB_HOST" -u "$DB_USER" -p"$DB_PASS" "$DB_NAME" -e "
            INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission)
            VALUES ('$user_id', '$conn_id', 'READ')
            ON DUPLICATE KEY UPDATE permission = 'READ'
        " 2>/dev/null || true
        log "Connection $conn_name assigned to $username"
    fi
    
    echo "{\"success\": true, \"message\": \"Instance deployed\", \"instance_num\": $instance_num}"
}

# Main logic
log "Request received: $REQUEST_METHOD $PATH_INFO"

# For now, this is a stub that will be called from PHP
# The actual PHP script will handle the request parsing and call shell commands if needed

exit 0
