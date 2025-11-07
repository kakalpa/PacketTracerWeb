#!/bin/bash
set -e

PROJECT_ROOT="/run/media/kalpa/9530f1e7-4f57-4bf2-b7f2-b03a2b8d41111/PT DEv/PacketTracerWeb"
cd "$PROJECT_ROOT"

# Test bulk user creation with containers
echo "=== Testing Bulk User Creation with Container Assignment ==="
echo ""

# Before
echo "Before bulk create:"
docker ps -a -f name=ptvnc --format "table {{.Names}}\t{{.Status}}" | sort
echo ""

# Create test users with containers
echo "Creating 3 test users with containers..."
curl -s -X POST http://localhost:5000/api/bulk-create-users \
  -H "Content-Type: application/json" \
  -d '{
    "users": [
      {"username": "testuser1", "password": "Test@123", "create_container": true},
      {"username": "testuser2", "password": "Test@123", "create_container": true},
      {"username": "testuser3", "password": "Test@123", "create_container": true}
    ]
  }' | python3 -m json.tool

echo ""
echo "Waiting 10 seconds for containers to start..."
sleep 10

# After
echo ""
echo "After bulk create:"
docker ps -a -f name=ptvnc --format "table {{.Names}}\t{{.Status}}" | sort

echo ""
echo "=== Checking Database Mapping ==="
docker exec guacamole-mariadb mysql -u ptdbuser -pptdbpass -D guacamole_db \
  -e "SELECT username, container_name, status FROM user_container_mapping ORDER BY created_at DESC LIMIT 5;"

echo ""
echo "=== Test Summary ==="
echo "Expected containers: ptvnc4, ptvnc5, ptvnc6 (auto-increment)"
echo "Actual containers:"
docker ps -a -f name=ptvnc --format "{{.Names}}" | sort | tail -3
