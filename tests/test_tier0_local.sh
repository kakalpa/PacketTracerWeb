#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m'

PASSED=0
FAILED=0

assert_eq() {
  local desc="$1"
  local actual="$2"
  local expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    echo -e "${GREEN}✓ PASS:${NC} $desc (got: $actual)"
    PASSED=$((PASSED + 1))
  else
    echo -e "${RED}✗ FAIL:${NC} $desc (expected: $expected, got: $actual)"
    FAILED=$((FAILED + 1))
  fi
}

assert_contains() {
  local desc="$1"
  local haystack="$2"
  local needle="$3"
  if [[ "$haystack" == *"$needle"* ]]; then
    echo -e "${GREEN}✓ PASS:${NC} $desc"
    PASSED=$((PASSED + 1))
  else
    echo -e "${RED}✗ FAIL:${NC} $desc (did not contain: $needle)"
    FAILED=$((FAILED + 1))
  fi
}

assert_not_contains() {
  local desc="$1"
  local haystack="$2"
  local needle="$3"
  if [[ "$haystack" != *"$needle"* ]]; then
    echo -e "${GREEN}✓ PASS:${NC} $desc"
    PASSED=$((PASSED + 1))
  else
    echo -e "${RED}✗ FAIL:${NC} $desc (unexpectedly contained: $needle)"
    FAILED=$((FAILED + 1))
  fi
}

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}        TIER 0 LOCAL VERIFICATION TEST SUITE          ${NC}"
echo -e "${BLUE}======================================================${NC}"
echo ""

# -----------------------------------------------------------------------------
echo -e "${YELLOW}TEST GROUP 1: Path Sanitization (PROP-C4-04)${NC}"
# -----------------------------------------------------------------------------
MATCHES=$(grep -rn "/run/media/kalpa" pt-management/ deploy.sh deploy-full.sh Scripts/ test-bulk-create.sh 2>/dev/null || true)
assert_eq "No hardcoded developer workstation paths in source/scripts" "$MATCHES" ""

# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}TEST GROUP 2: Unauthenticated Endpoint Protection (PROP-C4-02)${NC}"
# -----------------------------------------------------------------------------
PT_URL="https://localhost:5000"

# Health must remain public
STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/health")
assert_eq "GET /health is public (200)" "$STATUS" "200"

# Defaults must remain public
STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/api/env/defaults")
assert_eq "GET /api/env/defaults is public (200)" "$STATUS" "200"

# Mutating and protected endpoints MUST return 401 when unauthenticated
STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" -X POST "$PT_URL/api/containers")
assert_eq "POST /api/containers rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/api/containers")
assert_eq "GET /api/containers rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" -X POST "$PT_URL/api/users")
assert_eq "POST /api/users rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/api/users")
assert_eq "GET /api/users rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" -X POST "$PT_URL/api/users/bulk/delete")
assert_eq "POST /api/users/bulk/delete rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" -X DELETE "$PT_URL/api/users/testuser")
assert_eq "DELETE /api/users/<user> rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/api/env/config")
assert_eq "GET /api/env/config rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" -X POST "$PT_URL/api/upload/certificate")
assert_eq "POST /api/upload/certificate rejects unauthenticated (401)" "$STATUS" "401"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" -X POST "$PT_URL/api/upload/key")
assert_eq "POST /api/upload/key rejects unauthenticated (401)" "$STATUS" "401"

# Unauthenticated page routes redirect to login (302)
STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/dashboard")
assert_eq "GET /dashboard redirects to login (302)" "$STATUS" "302"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/settings")
assert_eq "GET /settings redirects to login (302)" "$STATUS" "302"

STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "$PT_URL/files")
assert_eq "GET /files redirects to login (302)" "$STATUS" "302"

# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}TEST GROUP 3: Authenticated Session Workflows (PROP-C4-02)${NC}"
# -----------------------------------------------------------------------------
# Login with invalid password fails without cookie
LOGIN_FAIL_STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" \
  -X POST "$PT_URL/login" -d "username=ptadmin&password=WrongPassword")
assert_eq "Login with invalid password fails (401)" "$LOGIN_FAIL_STATUS" "401"

# Login with valid ptadmin credentials into a fresh cookie jar
COOKIE_JAR=$(mktemp)
trap "rm -f $COOKIE_JAR" EXIT

LOGIN_RESP=$(curl -k -s -c "$COOKIE_JAR" -i \
  -X POST "$PT_URL/login" -d "username=ptadmin&password=IlovePT")
assert_contains "Valid login redirects to dashboard (302 Found)" "$LOGIN_RESP" "302"

# Verify authenticated access to /api/users
AUTH_USERS_RESP=$(curl -k -s -b "$COOKIE_JAR" "$PT_URL/api/users")
assert_contains "Authenticated GET /api/users returns success:true" "$AUTH_USERS_RESP" '"success":true'
assert_contains "Authenticated GET /api/users returns user list" "$AUTH_USERS_RESP" 'ptadmin'

# Verify authenticated access to /api/containers
AUTH_CONTAINERS_RESP=$(curl -k -s -b "$COOKIE_JAR" "$PT_URL/api/containers")
assert_contains "Authenticated GET /api/containers returns success:true" "$AUTH_CONTAINERS_RESP" '"success":true'
assert_contains "Authenticated GET /api/containers returns ptvnc container" "$AUTH_CONTAINERS_RESP" 'ptvnc'

# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}TEST GROUP 4: Secret Key Hardening (PROP-C4-03)${NC}"
# -----------------------------------------------------------------------------
LOG_CHECK=$(docker logs pt-management 2>&1 | grep "Generated cryptographically secure random SECRET_KEY" | head -n 1 || true)
assert_contains "Gunicorn startup logged secure random SECRET_KEY generation" "$LOG_CHECK" "Generated cryptographically secure random SECRET_KEY"

# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}TEST GROUP 5: Scoped Cleanup Safety Filters (PROP-C5-06)${NC}"
# -----------------------------------------------------------------------------
# Test the volume regex filter from cleanup-all.sh against active docker volumes
EXT_VOLUMES="jenkins_home minikube decepticon_postgres_data supabase_db_nist-csf-app"
for vol in $EXT_VOLUMES; do
  MATCH=$(echo "$vol" | grep -E '^(mariadb_data|dbdump|pt_opt|ptweb-vnc_.*)$' || true)
  assert_eq "Cleanup volume filter ignores host volume '$vol'" "$MATCH" ""
done

# Ensure project volumes ARE matched
PROJ_VOLUMES="mariadb_data dbdump pt_opt"
for vol in $PROJ_VOLUMES; do
  MATCH=$(echo "$vol" | grep -E '^(mariadb_data|dbdump|pt_opt|ptweb-vnc_.*)$' || true)
  assert_eq "Cleanup volume filter matches project volume '$vol'" "$MATCH" "$vol"
done

# Ensure container filter ignores external containers
EXT_CONTAINERS="my-postgres my-redis jenkins custom-app"
for c in $EXT_CONTAINERS; do
  MATCH=$(echo "$c" | grep -E '^(guacamole-mariadb|pt-guacd|pt-guacamole|pt-nginx1|pt-management|ptvnc.*)$' || true)
  assert_eq "Cleanup container filter ignores host container '$c'" "$MATCH" ""
done

# Ensure container filter matches project containers
PROJ_CONTAINERS="guacamole-mariadb pt-guacd pt-guacamole pt-nginx1 pt-management ptvnc1 ptvnc99"
for c in $PROJ_CONTAINERS; do
  MATCH=$(echo "$c" | grep -E '^(guacamole-mariadb|pt-guacd|pt-guacamole|pt-nginx1|pt-management|ptvnc.*)$' || true)
  assert_eq "Cleanup container filter matches project container '$c'" "$MATCH" "$c"
done

# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}TEST GROUP 6: Guacamole Connection SQL Deletion Syntax${NC}"
# -----------------------------------------------------------------------------
DB_CLI="mariadb"
if ! docker exec guacamole-mariadb which mariadb >/dev/null 2>&1; then
  DB_CLI="mysql"
fi

EXPLAIN_SQL="EXPLAIN DELETE FROM guacamole_connection_permission WHERE connection_id = 9999;"
EXPLAIN_RES=$(docker exec guacamole-mariadb $DB_CLI -u ptdbuser -pptdbpass -D guacamole_db -e "$EXPLAIN_SQL" 2>&1 || true)
assert_not_contains "Fixed DELETE query syntax is valid in MariaDB" "$EXPLAIN_RES" "ERROR"

BROKEN_SQL="EXPLAIN DELETE FROM guacamole_user_permission WHERE connection_id = 9999;"
BROKEN_RES=$(docker exec guacamole-mariadb $DB_CLI -u ptdbuser -pptdbpass -D guacamole_db -e "$BROKEN_SQL" 2>&1 || true)
assert_contains "Old query confirmed invalid (Unknown column connection_id)" "$BROKEN_RES" "Unknown column 'connection_id'"

# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}TEST GROUP 7: MariaDB Volume Persistence (PROP-C2-01)${NC}"
# -----------------------------------------------------------------------------
# Check if mariadb_data volume exists
VOL_EXISTS=$(docker volume ls --format '{{.Name}}' | grep -x 'mariadb_data' || true)
assert_eq "Named volume 'mariadb_data' exists" "$VOL_EXISTS" "mariadb_data"

# Check if guacamole-mariadb has mariadb_data mounted to /var/lib/mysql
MOUNT_DEST=$(docker inspect guacamole-mariadb --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Name}}{{end}}{{end}}')
assert_eq "guacamole-mariadb mounts mariadb_data to /var/lib/mysql" "$MOUNT_DEST" "mariadb_data"

# -----------------------------------------------------------------------------
echo -e "\n${YELLOW}TEST GROUP 8: Secure Student File Downloads & Isolation (Option D)${NC}"
# -----------------------------------------------------------------------------
# 1. Public /downloads/ must be eliminated (404/403)
DL_STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "https://localhost/downloads/")
assert_contains "Public /downloads/ directory listing is eliminated (404/403)" "404 403" "$DL_STATUS"

# 2. Internal downloads must reject direct external requests (404)
INT_STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "https://localhost/internal/downloads/ptvnc1/test.pkt")
assert_eq "Internal downloads endpoint blocks direct external access (404)" "$INT_STATUS" "404"

# 3. Test multi-tenant container isolation and secure download workflow
TEST_PKT="student-lab-$(date +%s).pkt"
TEST_DATA="PACKET_TRACER_LAB_DATA_CONTENT_$(date +%s)"
mkdir -p "shared/instances/ptvnc1"
echo "$TEST_DATA" > "shared/instances/ptvnc1/$TEST_PKT"

# Check isolation: visible in ptvnc1, NOT visible in ptvnc2
VIS_P1=$(docker exec ptvnc1 test -f "/shared/$TEST_PKT" && echo "YES" || echo "NO")
assert_eq "File is visible inside ptvnc1 (/shared)" "$VIS_P1" "YES"

VIS_P2=$(docker exec ptvnc2 test -f "/shared/$TEST_PKT" && echo "YES" || echo "NO")
assert_eq "File is ISOLATED and NOT visible in ptvnc2" "$VIS_P2" "NO"

# 4. Mint token via Student API
TOKEN_JSON=$(curl -k -s "https://localhost/api/student/files/token?container=ptvnc1&file=$TEST_PKT")
assert_contains "Student API token response has success:true" "$TOKEN_JSON" '"success":true'

DL_PATH=$(echo "$TOKEN_JSON" | grep -o '"download_url":"[^"]*' | cut -d'"' -f4)
assert_contains "Student API returns download URL" "$DL_PATH" "/api/student/files/download"

# 5. Execute secure zero-copy download via Nginx
DL_CONTENT=$(curl -k -s "https://localhost$DL_PATH")
assert_eq "Downloaded content matches original file content exactly" "$DL_CONTENT" "$TEST_DATA"

# 6. Verify path traversal attempt is blocked
TRAVERSAL_STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "https://localhost/api/student/files/download?container=ptvnc1&file=../../etc/passwd&expires=9999999999&sig=dummy")
assert_contains "Path traversal attempt is rejected (403/401)" "403 401" "$TRAVERSAL_STATUS"

# 7. Verify tampered signature is rejected
TAMPERED_PATH=$(echo "$DL_PATH" | sed 's/sig=[^&]*/sig=invalidsignature/')
TAMPERED_STATUS=$(curl -k -s -o /dev/null -w "%{http_code}" "https://localhost$TAMPERED_PATH")
assert_contains "Tampered download request is rejected (403/401)" "403 401" "$TAMPERED_STATUS"

# 8. Test Course Materials (/shared/common) distribution to all students
COMMON_PKT="course-material-$(date +%s).pkt"
COMMON_DATA="COURSE_MATERIAL_DATA_$(date +%s)"
echo "$COMMON_DATA" > "shared/common/$COMMON_PKT"

VIS_COMMON_1=$(docker exec ptvnc1 test -f "/home/ptuser/Desktop/Course_Materials/$COMMON_PKT" && echo "YES" || echo "NO")
assert_eq "Course material is visible on ptvnc1 Desktop (Course_Materials)" "$VIS_COMMON_1" "YES"

VIS_COMMON_2=$(docker exec ptvnc2 test -f "/home/ptuser/Desktop/Course_Materials/$COMMON_PKT" && echo "YES" || echo "NO")
assert_eq "Course material is visible on ptvnc2 Desktop (Course_Materials)" "$VIS_COMMON_2" "YES"

RO_TEST=$(docker exec ptvnc1 rm -f "/shared_common/$COMMON_PKT" 2>&1 || true)
assert_contains "Course materials are read-only in student session" "$RO_TEST" "Read-only file system"

COMMON_TOKEN_JSON=$(curl -k -s "https://localhost/api/student/files/token?container=common&file=$COMMON_PKT")
COMMON_DL_PATH=$(echo "$COMMON_TOKEN_JSON" | grep -o '"download_url":"[^"]*' | cut -d'"' -f4)
COMMON_DL_CONTENT=$(curl -k -s "https://localhost$COMMON_DL_PATH")
assert_eq "Course material downloadable via Student API" "$COMMON_DL_CONTENT" "$COMMON_DATA"

# Cleanup
rm -f "shared/instances/ptvnc1/$TEST_PKT"
rm -f "shared/common/$COMMON_PKT"

# -----------------------------------------------------------------------------
echo -e "\n${BLUE}======================================================${NC}"
echo -e "RESULTS: ${GREEN}$PASSED Passed${NC}, ${RED}$FAILED Failed${NC}"
echo -e "${BLUE}======================================================${NC}"

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
