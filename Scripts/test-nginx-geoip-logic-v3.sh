#!/bin/bash

# Updated test script to validate GeoIP filtering with trusted IP bypass

echo "================================"
echo "  GeoIP Filtering Logic Test (v3)"
echo "  With Trusted IP Bypass"
echo "================================"
echo ""

echo "Testing nginx filtering with trusted IP exception..."
echo ""

# Test cases: (remote_addr, allowed_country, blocked_country, should_block)
# Trusted IPs: 127.x, 10.x, 172.(16-31).x, 192.168.x
test_cases=(
    "127.0.0.1:1:0:false"              # Localhost - TRUSTED, ALLOW
    "127.0.0.2:0:0:false"              # Localhost - TRUSTED, ALLOW (even if blocked)
    "192.168.1.1:-1:0:false"           # Private (192.168) - TRUSTED, ALLOW
    "172.17.0.1:-1:0:false"            # Docker bridge (172.17) - TRUSTED, ALLOW
    "172.31.255.255:-1:0:false"        # Private (172.16-31) max - TRUSTED, ALLOW
    "10.0.0.1:-1:0:false"              # Private (10.0) - TRUSTED, ALLOW
    "8.8.8.8:1:0:false"                # Public USA (allowed_country=1) - PUBLIC, ALLOW
    "8.8.8.8:0:0:true"                 # Public blocked (allowed_country=0) - PUBLIC, BLOCK
    "8.26.56.26:-1:0:true"             # Public Germany unknown - PUBLIC, BLOCK
    "202.106.0.20:1:1:true"            # Public China in blocklist - PUBLIC, BLOCK
    "91.199.119.83:-1:0:true"          # Public Russia unknown - PUBLIC, BLOCK
    "200.0.0.1:1:0:false"              # Some public IP, allowed - PUBLIC, ALLOW
    "200.0.0.1:1:1:true"               # Some public IP, blocked - PUBLIC, BLOCK
)

passed=0
failed=0

for test in "${test_cases[@]}"; do
    IFS=':' read -r remote_addr allowed_country blocked_country expected_block <<< "$test"
    
    should_block=false
    allow_access=1
    
    # Check if this is a trusted IP
    if [[ $remote_addr =~ ^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.) ]]; then
        allow_access=1  # Trusted IPs bypass GeoIP filtering
    else
        # GeoIP checks for non-trusted IPs
        # Check BLOCK mode first
        if [ "$blocked_country" = "1" ]; then
            allow_access=0
        fi
        
        # Check ALLOW mode (whitelist)
        if [ "$allow_access" = "1" ] && [ "$allowed_country" != "1" ]; then
            allow_access=0
        fi
    fi
    
    if [ "$allow_access" = "0" ]; then
        should_block=true
    fi
    
    # Compare with expected
    if [ "$should_block" = "$expected_block" ]; then
        status="✅ PASS"
        ((passed++))
    else
        status="❌ FAIL"
        ((failed++))
    fi
    
    trust_status="TRUSTED" 
    if [[ ! $remote_addr =~ ^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.) ]]; then
        trust_status="PUBLIC"
    fi
    
    printf "%s %s %12s | allow=%d block=%d → BLOCK=%s (expected %s)\n" \
           "$status" "$remote_addr" "$trust_status" "$allowed_country" "$blocked_country" "$should_block" "$expected_block"
done

echo ""
echo "================================"
echo "Test Results: $passed passed, $failed failed"
echo "================================"

if [ $failed -eq 0 ]; then
    echo "✅ All logic tests passed!"
    exit 0
else
    echo "❌ Some tests failed!"
    exit 1
fi
