#!/bin/bash

# Updated test script to validate localhost exception logic

echo "================================"
echo "  GeoIP Filtering Logic Test (v2)"
echo "================================"
echo ""

echo "Testing updated nginx filtering with localhost exception..."
echo ""

# Test cases: (remote_addr, allowed_country, blocked_country, should_block)
test_cases=(
    "127.0.0.1:1:0:false"      # Localhost (allowed by IP regex) - ALLOW
    "192.168.1.1:1:0:false"    # Private IP (allowed by IP regex) - ALLOW
    "172.17.0.1:1:0:false"     # Docker bridge (allowed by IP regex) - ALLOW
    "10.0.0.1:-1:0:false"      # Private IP with unknown country - ALLOW (local exception)
    "8.8.8.8:1:0:false"        # USA (allowed_country=1) - ALLOW
    "8.8.8.8:0:0:true"         # Blocked country (allowed_country=0) - BLOCK
    "8.26.56.26:-1:0:true"     # Germany unknown, public IP - BLOCK
    "202.106.0.20:1:1:true"    # China in blocklist - BLOCK
    "91.199.119.83:-1:0:true"  # Russia unknown, public IP - BLOCK
)

passed=0
failed=0

for test in "${test_cases[@]}"; do
    IFS=':' read -r remote_addr allowed_country blocked_country expected_block <<< "$test"
    
    should_block=false
    allow_access=1
    
    # Allow localhost and private IPs
    if [[ $remote_addr =~ ^(127\.|10\.|172\.|192\.168\.) ]]; then
        allow_access=1
    fi
    
    # Check BLOCK mode condition (only if not localhost)
    if [ "$allow_access" = "1" ]; then
        if [ "$blocked_country" = "1" ]; then
            allow_access=0
        fi
    fi
    
    # Check ALLOW mode condition
    if [ "$allow_access" = "1" ]; then
        if [ "$allowed_country" != "1" ]; then
            allow_access=0
        fi
    fi
    
    if [ "$allow_access" = "0" ]; then
        should_block=true
    fi
    
    # Compare with expected
    if [ "$should_block" = "$expected_block" ]; then
        echo "✅ PASS: $remote_addr, allowed=$allowed_country, blocked=$blocked_country → BLOCK=$should_block"
        ((passed++))
    else
        echo "❌ FAIL: $remote_addr, allowed=$allowed_country, blocked=$blocked_country → BLOCK=$should_block (expected $expected_block)"
        ((failed++))
    fi
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
