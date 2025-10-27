#!/bin/bash

# Comprehensive test script for PacketTracer + Guacamole deployment
# Tests: Docker containers, networking, databases, shared folders, file downloads

echo -e "\e[32m╔════════════════════════════════════════════════╗\e[0m"
echo -e "\e[32m║  PacketTracer Deployment Test Suite           ║\e[0m"
echo -e "\e[32m╚════════════════════════════════════════════════╝\e[0m"
echo ""

# Color codes
RED='\e[31m'
GREEN='\e[32m'
YELLOW='\e[33m'
BLUE='\e[34m'
NC='\e[0m'

# Test counters
TESTS_PASSED=0
TESTS_FAILED=0

# Get actual running ptvnc instances
PTVNC_INSTANCES=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sort)
PTVNC_COUNT=$(echo "$PTVNC_INSTANCES" | wc -l)

# Get first and second instance for testing (use actual running instances)
PTVNC_FIRST=$(echo "$PTVNC_INSTANCES" | head -1)
PTVNC_SECOND=$(echo "$PTVNC_INSTANCES" | tail -1)

# Test function
run_test() {
    local test_name="$1"
    local test_cmd="$2"
    echo -n "Testing: $test_name... "
    
    if eval "$test_cmd" > /tmp/test_output.log 2>&1; then
        echo -e "${GREEN}✅ PASS${NC}"
        ((TESTS_PASSED++))
        return 0
    else
        echo -e "${RED}❌ FAIL${NC}"
        echo -e "${RED}Error:${NC}"
        cat /tmp/test_output.log | sed 's/^/  /'
        ((TESTS_FAILED++))
        return 1
    fi
}

# ============================================================================
# SECTION 1: DOCKER CONTAINERS
# ============================================================================
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 1: Docker Container Status${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "MariaDB container running" \
    "docker ps --filter 'name=guacamole-mariadb' --format '{{.State}}' | grep -q 'running'"

run_test "Guacd container running" \
    "docker ps --filter 'name=pt-guacd' --format '{{.State}}' | grep -q 'running'"

run_test "Guacamole container running" \
    "docker ps --filter 'name=pt-guacamole' --format '{{.State}}' | grep -q 'running'"

run_test "Nginx container running" \
    "docker ps --filter 'name=pt-nginx1' --format '{{.State}}' | grep -q 'running'"

run_test "$PTVNC_FIRST container running" \
    "docker ps --filter 'name=$PTVNC_FIRST' --format '{{.State}}' | grep -q 'running'"

run_test "$PTVNC_SECOND container running" \
    "docker ps --filter 'name=$PTVNC_SECOND' --format '{{.State}}' | grep -q 'running'"

# ============================================================================
# SECTION 2: DATABASE CONNECTIVITY
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 2: Database Connectivity${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "MariaDB is accessible" \
    "docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass -e 'SELECT 1' > /dev/null"

run_test "Guacamole database exists" \
    "docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass -e 'USE guacamole_db; SELECT 1' > /dev/null"

run_test "Guacamole connections table exists" \
    "docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -e 'SELECT COUNT(*) FROM guacamole_connection' > /dev/null"

run_test "At least 2 connections exist" \
    "[ \$(docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -sN -e 'SELECT COUNT(*) FROM guacamole_connection') -ge 2 ]"

# ============================================================================
# SECTION 3: SHARED FOLDER ACCESSIBILITY
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 3: Shared Folder Accessibility${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "Host /shared directory exists" \
    "[ -d '$(pwd)/shared' ]"

run_test "$PTVNC_FIRST /shared mount exists" \
    "docker exec $PTVNC_FIRST [ -d /shared ]"

run_test "$PTVNC_SECOND /shared mount exists" \
    "docker exec $PTVNC_SECOND [ -d /shared ]"

run_test "nginx /shared mount exists" \
    "docker exec pt-nginx1 [ -d /shared ]"

# ============================================================================
# SECTION 4: SHARED FOLDER WRITES
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 4: Shared Folder Write Permissions${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "Host can write to /shared" \
    "touch $(pwd)/shared/.test-host && rm $(pwd)/shared/.test-host"

run_test "$PTVNC_FIRST can write to /shared" \
    "docker exec $PTVNC_FIRST touch /shared/.test-$PTVNC_FIRST && docker exec $PTVNC_FIRST rm /shared/.test-$PTVNC_FIRST"

run_test "$PTVNC_SECOND can write to /shared" \
    "docker exec $PTVNC_SECOND touch /shared/.test-$PTVNC_SECOND && docker exec $PTVNC_SECOND rm /shared/.test-$PTVNC_SECOND"

# ============================================================================
# SECTION 5: DESKTOP SYMLINKS
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 5: Desktop Symlinks${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "$PTVNC_FIRST has Desktop directory" \
    "docker exec $PTVNC_FIRST [ -d /home/ptuser/Desktop ]"

run_test "$PTVNC_FIRST has shared symlink on Desktop" \
    "docker exec $PTVNC_FIRST [ -L /home/ptuser/Desktop/shared ]"

run_test "$PTVNC_FIRST shared symlink points to /shared" \
    "docker exec $PTVNC_FIRST readlink /home/ptuser/Desktop/shared | grep -q '^/shared\$'"

run_test "$PTVNC_SECOND has shared symlink on Desktop" \
    "docker exec $PTVNC_SECOND [ -L /home/ptuser/Desktop/shared ]"

run_test "$PTVNC_SECOND shared symlink is accessible" \
    "docker exec $PTVNC_SECOND [ -d /home/ptuser/Desktop/shared ]"

# ============================================================================
# SECTION 6: WEB ENDPOINTS
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 6: Web Endpoints${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "Guacamole root endpoint (HTTP 200)" \
    "curl -s -I http://localhost/ 2>&1 | grep -q 'HTTP/1.1 200'"

run_test "Downloads endpoint (HTTP 200)" \
    "curl -s -I http://localhost/downloads/ 2>&1 | grep -q 'HTTP/1.1 200'"

run_test "Downloads directory listing works" \
    "curl -s http://localhost/downloads/ 2>&1 | grep -q '<title>Index of /downloads/</title>'"

# ============================================================================
# SECTION 7: FILE DOWNLOAD WORKFLOW
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 7: File Download Workflow${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# Create test file
TEST_FILE="test-workflow-$(date +%s).pkt"
TEST_CONTENT="Test file created at $(date)"

run_test "Create test file in /shared from host" \
    "echo '$TEST_CONTENT' > '$(pwd)/shared/$TEST_FILE'"

run_test "File visible from $PTVNC_FIRST" \
    "docker exec $PTVNC_FIRST [ -f /shared/$TEST_FILE ]"

run_test "File visible from $PTVNC_SECOND" \
    "docker exec $PTVNC_SECOND [ -f /shared/$TEST_FILE ]"

run_test "File downloadable via /downloads/" \
    "curl -s http://localhost/downloads/$TEST_FILE 2>&1 | grep -q 'Test file'"

run_test "Downloaded file content matches" \
    "[ \"\$(curl -s http://localhost/downloads/$TEST_FILE)\" = \"$TEST_CONTENT\" ]"

# Cleanup test file
rm "$(pwd)/shared/$TEST_FILE" 2>/dev/null || true

# ============================================================================
# SECTION 8: HELPER SCRIPTS
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 8: Helper Scripts${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "deploy.sh exists" \
    "[ -f '$(pwd)/deploy.sh' ]"

run_test "add-instance.sh exists" \
    "[ -f '$(pwd)/add-instance.sh' ]"

run_test "generate-dynamic-connections.sh exists and is executable" \
    "[ -x '$(pwd)/generate-dynamic-connections.sh' ]"

run_test "tune_ptvnc.sh exists" \
    "[ -f '$(pwd)/tune_ptvnc.sh' ]"

# ============================================================================
# SECTION 9: DOCKER VOLUMES
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 9: Docker Volumes${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "pt_opt volume exists" \
    "docker volume ls | grep -q 'pt_opt'"

run_test "Packet Tracer installed in pt_opt" \
    "docker exec ptvnc1 [ -d /opt/pt ]"

# ============================================================================
# SECTION 10: GUACAMOLE DATABASE SCHEMA
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 10: Guacamole Database Schema${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "guacamole_user table has data" \
    "docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -sN -e 'SELECT COUNT(*) FROM guacamole_user' | grep -q '[1-9]'"

run_test "guacamole_connection table has connections" \
    "docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -sN -e 'SELECT COUNT(*) FROM guacamole_connection' | grep -q '[1-9]'"

run_test "Connection parameters exist" \
    "docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -sN -e 'SELECT COUNT(*) FROM guacamole_connection_parameter' | grep -q '[1-9]'"

# ============================================================================
# SECTION 11: DOCKER NETWORKING
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 11: Docker Networking${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "Guacamole can reach MariaDB" \
    "docker exec pt-guacamole bash -c 'nc -z guacamole-mariadb 3306 2>&1' || docker exec pt-guacamole bash -c 'mariadb -h mariadb -uroot 2>&1' | grep -q 'mariadb'"

run_test "Nginx can reach Guacamole" \
    "docker exec pt-nginx1 bash -c 'curl -s -o /dev/null -w \"%{http_code}\" http://guacamole:8080/guacamole/ | grep -q 200'"

# ============================================================================
# SUMMARY
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}TEST SUMMARY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

TOTAL_TESTS=$((TESTS_PASSED + TESTS_FAILED))

echo ""
echo -e "Total Tests: ${YELLOW}$TOTAL_TESTS${NC}"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  🎉 ALL TESTS PASSED! DEPLOYMENT IS HEALTHY  ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════╝${NC}"
    exit 0
else
    echo -e "${RED}╔════════════════════════════════════════════════╗${NC}"
    echo -e "${RED}║  ⚠️  SOME TESTS FAILED - CHECK ERRORS ABOVE   ║${NC}"
    echo -e "${RED}╚════════════════════════════════════════════════╝${NC}"
    exit 1
fi
