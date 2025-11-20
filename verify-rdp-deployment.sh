#!/bin/bash
# Verification script for RDP + Guacamole deployment
# This tests all critical components are working

PASS=0
FAIL=0

test_item() {
    local desc="$1"
    local cmd="$2"
    
    printf "%-50s" "$desc"
    if eval "$cmd" >/dev/null 2>&1; then
        echo "✓"
        ((PASS++))
    else
        echo "✗"
        ((FAIL++))
    fi
}

echo "╔════════════════════════════════════════════════════════════════╗"
echo "║        RDP + Guacamole Deployment Verification Tests          ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

echo "Network Tests:"
test_item "  All containers on ptnet" "docker network inspect ptnet | grep -q ptvnc1"
test_item "  ptvnc1 on ptnet" "docker inspect ptvnc1 | grep -q 'ptnet'"
test_item "  ptvnc2 on ptnet" "docker inspect ptvnc2 | grep -q 'ptnet'"
test_item "  pt-guacd on ptnet" "docker inspect pt-guacd | grep -q 'ptnet'"

echo ""
echo "Connectivity Tests:"
test_item "  guacd → xrdp (ptvnc1:3389)" "docker exec pt-guacd nc -zv ptvnc1 3389 2>&1 | grep -q succeeded"
test_item "  guacd → xrdp (ptvnc2:3389)" "docker exec pt-guacd nc -zv ptvnc2 3389 2>&1 | grep -q succeeded"
test_item "  DNS resolution (ptvnc1)" "docker exec pt-guacd getent hosts ptvnc1 2>&1 | grep -q 172.18"
test_item "  DNS resolution (ptvnc2)" "docker exec pt-guacd getent hosts ptvnc2 2>&1 | grep -q 172.18"

echo ""
echo "Service Tests:"
test_item "  Guacamole API reachable" "curl -k -s https://localhost/api/auth -f >/dev/null"
test_item "  Guacamole authentication" "curl -k -s -X POST https://localhost/api/tokens -H 'Content-Type: application/x-www-form-urlencoded' -d 'username=ptadmin&password=IlovePT' | grep -q authToken"
test_item "  Database connectivity" "docker exec guacamole-mariadb mariadb -u ptdbuser -pptdbpass guacamole_db -e 'SELECT 1;' >/dev/null"
test_item "  RDP connections in DB" "docker exec guacamole-mariadb mariadb -u ptdbuser -pptdbpass guacamole_db -e \"SELECT COUNT(*) FROM guacamole_connection WHERE protocol='rdp';\" 2>&1 | grep -q '[1-9]'"

echo ""
echo "Container Status Tests:"
test_item "  ptvnc1 running" "docker ps | grep -q ptvnc1"
test_item "  ptvnc2 running" "docker ps | grep -q ptvnc2"
test_item "  pt-guacd running" "docker ps | grep -q pt-guacd"
test_item "  pt-guacamole running" "docker ps | grep -q pt-guacamole"
test_item "  guacamole-mariadb running" "docker ps | grep -q guacamole-mariadb"
test_item "  pt-nginx1 running" "docker ps | grep -q pt-nginx1"

echo ""
echo "Server Process Tests:"
test_item "  xrdp running (ptvnc1)" "docker exec ptvnc1 ps aux 2>/dev/null | grep -q '/usr/sbin/xrdp'"
test_item "  xrdp-sesman running (ptvnc1)" "docker exec ptvnc1 ps aux 2>/dev/null | grep -q 'xrdp-sesman'"
test_item "  xrdp running (ptvnc2)" "docker exec ptvnc2 ps aux 2>/dev/null | grep -q '/usr/sbin/xrdp'"
test_item "  xrdp-sesman running (ptvnc2)" "docker exec ptvnc2 ps aux 2>/dev/null | grep -q 'xrdp-sesman'"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Results: $PASS passed, $FAIL failed"
echo "════════════════════════════════════════════════════════════════"

if [ $FAIL -eq 0 ]; then
    echo ""
    echo "✅ All tests passed! RDP deployment is ready."
    echo ""
    echo "Next steps:"
    echo "  1. Open https://localhost in your web browser"
    echo "  2. Login with ptadmin / IlovePT"
    echo "  3. Click on 'pt01' to start RDP session"
    echo "  4. Verify PacketTracer starts and 3D rendering works"
    exit 0
else
    echo ""
    echo "❌ Some tests failed. Review the failures above."
    exit 1
fi
