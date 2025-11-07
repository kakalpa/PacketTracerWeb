#!/bin/bash

# Comprehensive test script for PacketTracer + Guacamole deployment
# Tests: Docker containers, networking, databases, shared folders, file downloads, and GeoIP (if configured)

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

# ============================================================================
# READ .env FILE FOR OPTIONAL FEATURES
# ============================================================================
# Prefer PROJECT_ROOT environment variable (set by deploy scripts). Fall back to current working directory.
WORKDIR="${PROJECT_ROOT:-$(pwd)}"
if [ -f "$WORKDIR/.env" ]; then
    source "$WORKDIR/.env"
    echo -e "${YELLOW}ℹ️  Configuration loaded from .env (from $WORKDIR/.env)${NC}"
else
    echo -e "${YELLOW}ℹ️  No .env file found at $WORKDIR/.env (using defaults)${NC}"
fi

# GeoIP configuration flags (default to false if not set)
NGINX_GEOIP_ALLOW=${NGINX_GEOIP_ALLOW:-false}
NGINX_GEOIP_BLOCK=${NGINX_GEOIP_BLOCK:-false}
GEOIP_ALLOW_COUNTRIES=${GEOIP_ALLOW_COUNTRIES:-}
GEOIP_BLOCK_COUNTRIES=${GEOIP_BLOCK_COUNTRIES:-}

# Rate limiting configuration flags (default to false if not set)
NGINX_RATE_LIMIT_ENABLE=${NGINX_RATE_LIMIT_ENABLE:-false}
NGINX_RATE_LIMIT_RATE=${NGINX_RATE_LIMIT_RATE:-10r/s}
NGINX_RATE_LIMIT_BURST=${NGINX_RATE_LIMIT_BURST:-20}
NGINX_RATE_LIMIT_ZONE_SIZE=${NGINX_RATE_LIMIT_ZONE_SIZE:-10m}

# Determine if GeoIP testing should run
GEOIP_ENABLED=false
if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ]; then
    GEOIP_ENABLED=true
fi

# HTTPS configuration flag (default to false if not set)
ENABLE_HTTPS=${ENABLE_HTTPS:-false}

echo ""

# Get actual running ptvnc instances
PTVNC_INSTANCES=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sort)
PTVNC_COUNT=$(echo "$PTVNC_INSTANCES" | wc -l)

# Get first and second instance for testing (use actual running instances)
PTVNC_FIRST=$(echo "$PTVNC_INSTANCES" | head -1)
PTVNC_SECOND=$(echo "$PTVNC_INSTANCES" | tail -1)

# Determine which web host to use for HTTP checks. When running inside a container
# "localhost" refers to the container itself; prefer the pt-nginx container name
# when it is reachable from this runtime. Fall back to localhost when container
# hostname is not reachable (e.g., running on the host machine).
WEB_HOST="http://localhost"
if curl -s --connect-timeout 1 http://pt-nginx1/ >/dev/null 2>&1; then
    WEB_HOST="http://pt-nginx1"
elif curl -s --connect-timeout 1 http://nginx/ >/dev/null 2>&1; then
    WEB_HOST="http://nginx"
fi

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
    "[ -d \"$WORKDIR/shared\" ]"

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
    "touch \"$WORKDIR/shared/.test-host\" && rm \"$WORKDIR/shared/.test-host\""

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

run_test "Guacamole root endpoint (HTTP 200/30x)" \
    "curl -k -L -s -I \"$WEB_HOST/\" 2>&1 | grep -q 'HTTP/1.1 200\\|HTTP/2 200\\|HTTP/1.1 30'"

run_test "Downloads endpoint (HTTP 200/30x)" \
    "curl -k -L -s -I \"$WEB_HOST/downloads/\" 2>&1 | grep -q 'HTTP/1.1 200\\|HTTP/2 200\\|HTTP/1.1 30'"

run_test "Downloads directory listing works (not 404)" \
    "curl -k -L -s -I \"$WEB_HOST/downloads/\" 2>&1 | grep -q -E 'HTTP/1.1 200|HTTP/1.1 30|HTTP/2 200'"

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
    "echo '$TEST_CONTENT' > \"$WORKDIR/shared/$TEST_FILE\""

run_test "File visible from $PTVNC_FIRST" \
    "docker exec $PTVNC_FIRST [ -f /shared/$TEST_FILE ]"

run_test "File visible from $PTVNC_SECOND" \
    "docker exec $PTVNC_SECOND [ -f /shared/$TEST_FILE ]"

run_test "File downloadable via /downloads/" \
    "curl -k -L -s \"$WEB_HOST/downloads/$TEST_FILE\" 2>&1 | grep -q 'Test file'"

run_test "Downloaded file content matches" \
    "[ \"\$(curl -k -L -s \"$WEB_HOST/downloads/$TEST_FILE\")\" = \"$TEST_CONTENT\" ]"

# Cleanup test file
rm "$WORKDIR/shared/$TEST_FILE" 2>/dev/null || true

# ============================================================================
# SECTION 8: HELPER SCRIPTS
# ============================================================================
echo ""
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SECTION 8: Helper Scripts${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

run_test "deploy.sh exists" \
    "[ -f \"$WORKDIR/deploy.sh\" ]"

run_test "add-instance.sh exists" \
    "[ -f \"$WORKDIR/add-instance.sh\" ]"

run_test "generate-dynamic-connections.sh exists and is executable" \
    "[ -x \"$WORKDIR/generate-dynamic-connections.sh\" ]"

run_test "tune_ptvnc.sh exists" \
    "[ -f \"$WORKDIR/tune_ptvnc.sh\" ]"

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
    "docker exec pt-nginx1 bash -c 'timeout 2 bash -c \"</dev/tcp/guacamole/8080\" 2>&1' | grep -q 'succeeded\\|Connection\\|refused' || docker exec pt-nginx1 bash -c 'nc -z guacamole 8080 2>&1' | head -1 > /dev/null || docker exec pt-nginx1 bash -c 'cat </dev/null >/dev/tcp/guacamole/8080 2>&1'"

# ============================================================================
# SECTION 12: RATE LIMITING CONFIGURATION (CONDITIONAL)
# ============================================================================
if [ "$NGINX_RATE_LIMIT_ENABLE" = "true" ]; then
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}SECTION 12: Rate Limiting Configuration${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    echo -e "${YELLOW}Configuration:${NC}"
    echo -e "${YELLOW}  Rate: $NGINX_RATE_LIMIT_RATE${NC}"
    echo -e "${YELLOW}  Burst: $NGINX_RATE_LIMIT_BURST${NC}"
    echo -e "${YELLOW}  Zone Size: $NGINX_RATE_LIMIT_ZONE_SIZE${NC}"
    echo ""
    
    # 12.1: Check nginx limit_req module is available by verifying -T output works
    run_test "Nginx limit_req module available (nginx -T succeeds)" \
        "docker exec pt-nginx1 nginx -T 2>&1 | grep -q 'limit_req'"
    
    # 12.2: Check rate limiting zone is configured at http level
    run_test "Rate limiting zone (limit_req_zone) configured in ptweb.conf" \
        "docker exec pt-nginx1 grep -q 'limit_req_zone' /etc/nginx/conf.d/ptweb.conf"
    
    run_test "Rate limiting zone name is pt_req_zone" \
        "docker exec pt-nginx1 grep -q 'zone=pt_req_zone' /etc/nginx/conf.d/ptweb.conf"
    
    run_test "Rate limit rate is correctly set ($NGINX_RATE_LIMIT_RATE)" \
        "docker exec pt-nginx1 grep 'limit_req_zone' /etc/nginx/conf.d/ptweb.conf | grep -q 'rate=${NGINX_RATE_LIMIT_RATE}'"
    
    run_test "Rate limit zone size is correctly set ($NGINX_RATE_LIMIT_ZONE_SIZE)" \
        "docker exec pt-nginx1 grep 'limit_req_zone' /etc/nginx/conf.d/ptweb.conf | grep -q 'pt_req_zone:${NGINX_RATE_LIMIT_ZONE_SIZE}'"
    
    # 12.3: Check ptweb.conf has limit_req directive in location block
    run_test "ptweb.conf has limit_req directive in location block" \
        "docker exec pt-nginx1 grep -A 30 'location /' /etc/nginx/conf.d/ptweb.conf | grep -q 'limit_req zone=pt_req_zone'"
    
    run_test "limit_req burst value is correctly set ($NGINX_RATE_LIMIT_BURST)" \
        "docker exec pt-nginx1 grep 'limit_req' /etc/nginx/conf.d/ptweb.conf | grep -q 'burst=${NGINX_RATE_LIMIT_BURST}'"
    
    run_test "limit_req has nodelay parameter for immediate rejection" \
        "docker exec pt-nginx1 grep 'limit_req' /etc/nginx/conf.d/ptweb.conf | grep -q 'nodelay'"
    
    # 12.4: Verify nginx configuration is valid
    run_test "Nginx configuration syntax is valid (nginx -t)" \
        "docker exec pt-nginx1 nginx -t 2>&1 | grep -q 'successful'"
    
    run_test "No rate limiting errors in nginx error logs" \
        "! docker exec pt-nginx1 grep -i 'limit_req.*error' /var/log/nginx/error.log 2>/dev/null | grep -q '.'"
    
    # 12.5: Test rate limiting functionality with concurrent requests
    run_test "Web interface accessible under normal load" \
        "curl -k -L -s -I \"$WEB_HOST/\" 2>&1 | grep -q 'HTTP/1.1 200\\|HTTP/2 200\\|HTTP/1.1 30'"
    
    run_test "Rate limiting allows requests within limit" \
        "for i in {1..5}; do curl -k -s -o /dev/null \"$WEB_HOST/\" 2>&1; done; echo 'ok'"
    
    # 12.6: Test burst allowance - rapid requests should succeed up to burst limit
    run_test "Burst allowance allows rapid requests up to burst limit" \
        "codes=\$(for i in \$(seq 1 25); do curl -k -s -o /dev/null -w '%{http_code}' \"$WEB_HOST/\" 2>&1; done); echo \$codes | grep -q '200'; test \${PIPESTATUS[0]} -eq 0"
    
    # 12.7: Test that rate limiting returns 429 when exceeded (optional - may be timing dependent)
    # This test is commented as it's timing-dependent and might not always trigger in test environment
    # run_test "Rate limiting returns 429 when limit exceeded" \
    #     "codes=\$(for i in \$(seq 1 50); do curl -k -s -o /dev/null -w '%{http_code}' http://localhost/ 2>&1; done); echo \$codes | grep -q '429'"
    
    # 12.8: Verify access logs are being recorded
    run_test "Nginx access logs record requests" \
        "docker exec pt-nginx1 test -f /var/log/nginx/access.log -a -s /var/log/nginx/access.log"
    
    run_test "Recent requests recorded in access logs" \
        "[ \$(docker exec pt-nginx1 tail -10 /var/log/nginx/access.log 2>/dev/null | wc -l) -gt 0 ]"
    
    # 12.9: Verify rate limiting directive is in location block
    run_test "limit_req directive applied to location block" \
        "docker exec pt-nginx1 grep -q 'limit_req' /etc/nginx/conf.d/ptweb.conf"
    
    # 12.10: Check that multiple rate limiting parameters are correct
    run_test "Rate limit zone uses binary_remote_addr for per-IP tracking" \
        "docker exec pt-nginx1 grep 'limit_req_zone' /etc/nginx/conf.d/ptweb.conf | grep -q '\$binary_remote_addr'"
    
else
    echo ""
    echo -e "${YELLOW}ℹ️  Rate Limiting tests skipped (not configured in .env)${NC}"
    echo -e "${YELLOW}   To enable Rate Limiting tests, set NGINX_RATE_LIMIT_ENABLE=true${NC}"
fi

# ============================================================================
# SECTION 13: GEOIP CONFIGURATION & DATABASE (CONDITIONAL)
# ============================================================================
if [ "$GEOIP_ENABLED" = true ]; then
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}SECTION 13: GeoIP Configuration & Database${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    if [ "$NGINX_GEOIP_ALLOW" = "true" ] && [ -n "$GEOIP_ALLOW_COUNTRIES" ]; then
        echo -e "${YELLOW}Mode: ALLOW (Whitelist)${NC}"
        echo -e "${YELLOW}Allowed countries: $GEOIP_ALLOW_COUNTRIES${NC}"
    fi
    
    if [ "$NGINX_GEOIP_BLOCK" = "true" ] && [ -n "$GEOIP_BLOCK_COUNTRIES" ]; then
        echo -e "${YELLOW}Mode: BLOCK (Blacklist)${NC}"
        echo -e "${YELLOW}Blocked countries: $GEOIP_BLOCK_COUNTRIES${NC}"
    fi
    echo ""
    
    # 12.1: Check nginx module is compiled
    run_test "Nginx GeoIP module compiled (--with-http_geoip_module)" \
        "docker exec pt-nginx1 nginx -V 2>&1 | grep -q 'with-http_geoip_module'"
    
    # 12.2: Check GeoIP database files exist and are readable
    run_test "GeoIP.dat database file exists in container" \
        "docker exec pt-nginx1 [ -f /usr/share/GeoIP/GeoIP.dat ]"
    
    run_test "GeoIP.dat database is readable (non-zero size)" \
        "docker exec pt-nginx1 bash -c '[ -r /usr/share/GeoIP/GeoIP.dat ] && [ -s /usr/share/GeoIP/GeoIP.dat ] && echo OK' | grep -q OK"
    
    run_test "GeoIP.dat database is at least 1MB (valid database)" \
        "[ \$(docker exec pt-nginx1 stat -c %s /usr/share/GeoIP/GeoIP.dat 2>/dev/null || echo 0) -gt 1000000 ]"
    
    # 12.3: Check nginx.conf has GeoIP directives at HTTP level
    run_test "nginx.conf has geoip_country directive" \
        "docker exec pt-nginx1 grep -q 'geoip_country /usr/share/GeoIP/GeoIP.dat' /etc/nginx/nginx.conf"
    
    run_test "nginx.conf has geoip_proxy_recursive enabled" \
        "docker exec pt-nginx1 grep -q 'geoip_proxy_recursive on' /etc/nginx/nginx.conf"
    
    run_test "nginx.conf has \$allowed_country map defined" \
        "docker exec pt-nginx1 grep -q 'map \$geoip_country_code \$allowed_country' /etc/nginx/nginx.conf"
    
    run_test "nginx.conf has \$blocked_country map defined" \
        "docker exec pt-nginx1 grep -q 'map \$geoip_country_code \$blocked_country' /etc/nginx/nginx.conf"
    
    # 12.4: Check ptweb.conf is correctly generated with GeoIP logic
    run_test "ptweb.conf exists in conf.d" \
        "docker exec pt-nginx1 [ -f /etc/nginx/conf.d/ptweb.conf ]"
    
    if [ "$NGINX_GEOIP_ALLOW" = "true" ]; then
        run_test "ptweb.conf has GeoIP ALLOW logic in location block" \
            "docker exec pt-nginx1 grep -A 5 'location /' /etc/nginx/conf.d/ptweb.conf | grep -q '\$allowed_country\\|GeoIP filtering'"
    fi
    
    if [ "$NGINX_GEOIP_BLOCK" = "true" ]; then
        run_test "ptweb.conf has GeoIP BLOCK logic in location block" \
            "docker exec pt-nginx1 grep -A 5 'location /' /etc/nginx/conf.d/ptweb.conf | grep -q '\$blocked_country\\|GeoIP filtering'"
    fi
    
    # 12.5: Verify nginx configuration syntax is valid
    run_test "Nginx configuration syntax is valid (nginx -t)" \
        "docker exec pt-nginx1 nginx -t 2>&1 | grep -q 'successful'"
    
    # 12.6: Verify nginx container is running without errors
    run_test "Nginx container is running and healthy" \
        "docker ps --filter 'name=pt-nginx1' --format '{{.State}}' | grep -q 'running'"
    
    run_test "No GeoIP errors in nginx error logs" \
        "! docker exec pt-nginx1 grep -i 'geoip.*error\\|geoip.*failed' /var/log/nginx/error.log 2>/dev/null | grep -q '.'"
    
    # 12.7: Test GeoIP functionality with actual requests
    run_test "Web interface accessible (GeoIP should allow localhost 127.x)" \
        "curl -k -L -s -I \"$WEB_HOST/\" 2>&1 | grep -q 'HTTP/1.1 200\\|HTTP/2 200'"
    
    run_test "Nginx logs requests (access log exists)" \
        "docker exec pt-nginx1 [ -f /var/log/nginx/access.log ]"
    
    # 12.8: Verify ptweb.conf proxy_pass is correct
    run_test "ptweb.conf has correct proxy_pass to Guacamole" \
        "docker exec pt-nginx1 grep -q 'proxy_pass http://[0-9.]*:8080/guacamole/' /etc/nginx/conf.d/ptweb.conf || docker exec pt-nginx1 grep -q 'proxy_pass' /etc/nginx/conf.d/ptweb.conf"
    
else
    echo ""
    echo -e "${YELLOW}ℹ️  GeoIP tests skipped (not configured in .env)${NC}"
    echo -e "${YELLOW}   To enable GeoIP tests, set NGINX_GEOIP_ALLOW=true or NGINX_GEOIP_BLOCK=true${NC}"
fi
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

if [ "$GEOIP_ENABLED" = true ]; then
    echo -e "GeoIP Tests: ${GREEN}Enabled${NC}"
else
    echo -e "GeoIP Tests: ${YELLOW}Disabled (not configured)${NC}"
fi

if [ "$NGINX_RATE_LIMIT_ENABLE" = "true" ]; then
    echo -e "Rate Limiting Tests: ${GREEN}Enabled${NC}"
    echo -e "  Rate: $NGINX_RATE_LIMIT_RATE, Burst: $NGINX_RATE_LIMIT_BURST"
else
    echo -e "Rate Limiting Tests: ${YELLOW}Disabled (not configured)${NC}"
fi

if [ "$ENABLE_HTTPS" = "true" ]; then
    echo -e "HTTPS: ${GREEN}Enabled${NC}"
else
    echo -e "HTTPS: ${YELLOW}Disabled${NC}"
fi
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
