<?php
/**
 * Bulk User & Instance Management API
 * 
 * This is a simple wrapper that:
 * 1. Creates users in the Guacamole database
 * 2. Deploys containers for each user
 * 3. Assigns connections to users
 */

header('Content-Type: application/json');

// Check if action is specified
$action = $_REQUEST['action'] ?? 'status';

// Verify admin credentials
$adminUser = $_REQUEST['adminUser'] ?? '';
$adminPass = $_REQUEST['adminPass'] ?? '';

// Simple credential check
$ADMIN_USER = 'admin';
$ADMIN_PASS = 'admin123';

if (!in_array($action, ['status']) && ($adminUser !== $ADMIN_USER || $adminPass !== $ADMIN_PASS)) {
    http_response_code(401);
    echo json_encode(['success' => false, 'message' => 'Invalid admin credentials']);
    exit;
}

// Database configuration
$DB_HOST = 'mariadb';
$DB_USER = 'ptdbuser';
$DB_PASS = 'ptdbpass';
$DB_NAME = 'guacamole_db';

// Parse CSV file
function parseCSV() {
    if (!isset($_FILES['csvFile'])) {
        return null;
    }

    $file = $_FILES['csvFile']['tmp_name'];
    if (!file_exists($file)) {
        return null;
    }

    $users = [];
    $handle = fopen($file, 'r');
    
    // Skip header
    fgetcsv($handle);
    
    while (($row = fgetcsv($handle)) !== false) {
        if (count($row) >= 2 && !empty($row[0]) && !empty($row[1])) {
            $users[] = [
                'username' => trim($row[0]),
                'password' => trim($row[1])
            ];
        }
    }
    
    fclose($handle);
    return $users;
}

// Create user in Guacamole database
function createGuacamoleUser($username, $password, $conn) {
    try {
        // Generate salt and hash password
        $salt = random_bytes(16);
        $hash = hash('sha256', $password . bin2hex($salt), true);
        
        // Check if user exists
        $stmt = $conn->prepare('SELECT entity_id FROM guacamole_entity WHERE name = ?');
        $stmt->bind_param('s', $username);
        $stmt->execute();
        $result = $stmt->get_result();
        
        if ($result->num_rows > 0) {
            return ['success' => true, 'message' => "User $username already exists"];
        }
        
        // Insert entity
        $stmt = $conn->prepare('INSERT INTO guacamole_entity (name, type) VALUES (?, "USER")');
        $stmt->bind_param('s', $username);
        $stmt->execute();
        $entity_id = $conn->insert_id;
        
        // Insert user with hashed password
        $stmt = $conn->prepare('INSERT INTO guacamole_user (entity_id, password_hash, password_salt, password_date) VALUES (?, ?, ?, NOW())');
        $stmt->bind_param('iss', $entity_id, $hash, $salt);
        $stmt->execute();
        
        return ['success' => true, 'message' => "User $username created"];
    } catch (Exception $e) {
        return ['success' => false, 'message' => 'DB Error: ' . $e->getMessage()];
    }
}

// Execute shell command and return output
function executeCommand($cmd) {
    $output = shell_exec($cmd . ' 2>&1');
    return $output;
}

// Deploy instance for user
function deployInstance($username, $workdir) {
    try {
        // Call add-instance.sh to create container
        $output = executeCommand("cd '$workdir' && bash ./add-instance.sh 1");
        
        // Parse output to get instance number
        preg_match('/Creating ptvnc(\d+)/', $output, $matches);
        $instance_num = $matches[1] ?? null;
        
        if (!$instance_num) {
            return ['success' => false, 'message' => 'Failed to parse instance number', 'output' => $output];
        }
        
        // Call generate-dynamic-connections to register in Guacamole
        $output = executeCommand("cd '$workdir' && bash ./generate-dynamic-connections.sh");
        
        return [
            'success' => true,
            'message' => "Instance ptvnc$instance_num deployed",
            'instance_num' => $instance_num
        ];
    } catch (Exception $e) {
        return ['success' => false, 'message' => 'Error: ' . $e->getMessage()];
    }
}

// Assign connection to user
function assignConnectionToUser($username, $connectionName, $conn) {
    try {
        // Get user entity_id
        $stmt = $conn->prepare('SELECT entity_id FROM guacamole_entity WHERE name = ?');
        $stmt->bind_param('s', $username);
        $stmt->execute();
        $result = $stmt->get_result()->fetch_assoc();
        
        if (!$result) {
            return ['success' => false, 'message' => "User $username not found"];
        }
        
        $user_id = $result['entity_id'];
        
        // Get connection_id
        $stmt = $conn->prepare('SELECT connection_id FROM guacamole_connection WHERE connection_name = ?');
        $stmt->bind_param('s', $connectionName);
        $stmt->execute();
        $result = $stmt->get_result()->fetch_assoc();
        
        if (!$result) {
            return ['success' => false, 'message' => "Connection $connectionName not found"];
        }
        
        $connection_id = $result['connection_id'];
        
        // Grant READ permission
        $permission = 'READ';
        $stmt = $conn->prepare('INSERT INTO guacamole_connection_permission (entity_id, connection_id, permission) VALUES (?, ?, ?) ON DUPLICATE KEY UPDATE permission = VALUES(permission)');
        $stmt->bind_param('iss', $user_id, $connection_id, $permission);
        $stmt->execute();
        
        return ['success' => true, 'message' => "Connection assigned"];
    } catch (Exception $e) {
        return ['success' => false, 'message' => 'DB Error: ' . $e->getMessage()];
    }
}

// Get current status
function getStatus($conn) {
    try {
        // Count users
        $result = $conn->query('SELECT COUNT(*) as count FROM guacamole_user');
        $users = $result->fetch_assoc()['count'];
        
        // Count containers
        $output = shell_exec('docker ps --format "table {{.Names}}" | grep "^ptvnc" | wc -l 2>&1');
        $containers = trim($output);
        
        return [
            'success' => true,
            'users' => $users,
            'containers' => $containers
        ];
    } catch (Exception $e) {
        return ['success' => false, 'message' => $e->getMessage()];
    }
}

// Main logic
try {
    $conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS, $DB_NAME);
    
    if ($conn->connect_error) {
        http_response_code(500);
        echo json_encode(['success' => false, 'message' => 'Database connection failed']);
        exit;
    }
    
    if ($action === 'create') {
        // Create users
        $users = parseCSV();
        
        if (!$users) {
            http_response_code(400);
            echo json_encode(['success' => false, 'message' => 'Invalid CSV file']);
            exit;
        }
        
        $results = [];
        foreach ($users as $user) {
            $result = createGuacamoleUser($user['username'], $user['password'], $conn);
            $results[] = [
                'username' => $user['username'],
                ...$result
            ];
        }
        
        $success_count = count(array_filter($results, fn($r) => $r['success']));
        echo json_encode([
            'success' => true,
            'action' => 'create',
            'message' => "Successfully created $success_count/" . count($users) . " users",
            'results' => $results
        ]);
        
    } else if ($action === 'deploy') {
        // Deploy instances
        $users = parseCSV();
        
        if (!$users) {
            http_response_code(400);
            echo json_encode(['success' => false, 'message' => 'Invalid CSV file']);
            exit;
        }
        
        $workdir = dirname(__FILE__) . '/../../..';
        $results = [];
        
        foreach ($users as $user) {
            $deploy_result = deployInstance($user['username'], $workdir);
            $results[] = [
                'username' => $user['username'],
                ...$deploy_result
            ];
            
            // If deployment succeeded, assign connection
            if ($deploy_result['success'] && isset($deploy_result['instance_num'])) {
                $conn_name = 'pt' . str_pad($deploy_result['instance_num'], 2, '0', STR_PAD_LEFT);
                assignConnectionToUser($user['username'], $conn_name, $conn);
            }
        }
        
        $success_count = count(array_filter($results, fn($r) => $r['success']));
        echo json_encode([
            'success' => true,
            'action' => 'deploy',
            'message' => "Successfully deployed $success_count/" . count($users) . " instances",
            'results' => $results
        ]);
        
    } else if ($action === 'status') {
        $status = getStatus($conn);
        echo json_encode($status);
    }
    
    $conn->close();
    
} catch (Exception $e) {
    http_response_code(500);
    echo json_encode(['success' => false, 'message' => $e->getMessage()]);
}
?>
