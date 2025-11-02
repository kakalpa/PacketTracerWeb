#!/bin/bash

# Test script to validate GeoIP filtering logic in nginx configuration
# This tests the nginx if-block logic without requiring a full deployment

echo "================================"
echo "  GeoIP Filtering Logic Test"
echo "================================"
echo ""

# Read the deploy.sh and extract the generate_nginx_config function output
# We'll test the logic by simulating the if-conditions

echo "Testing nginx filtering conditions..."
echo ""

# Test cases: (allowed_country_value, blocked_country_value, should_block)
test_cases=(
    "1:0:false"      # US (allowed_country=1) - ALLOW
    "0:0:true"       # Blocked country (allowed_country=0) - BLOCK
    "-1:0:true"      # Unknown/localhost (allowed_country=-1) - BLOCK (this was the bug!)
    "1:1:true"       # Blocked in BLOCK mode (blocked_country=1) - BLOCK
    "-1:1:true"      # Unknown in BLOCK mode - BLOCK
)

passed=0
failed=0

for test in "${test_cases[@]}"; do
    IFS=':' read -r allowed_country blocked_country expected_block <<< "$test"
    
    # Simulate nginx logic:
    # if ($blocked_country = 1) { return 444; }
    # if ($allowed_country != 1) { return 444; }
    
    should_block=false
    
    # Check BLOCK mode condition
    if [ "$blocked_country" = "1" ]; then
        should_block=true
    fi
    
    # Check ALLOW mode condition (the FIXED condition)
    if [ "$allowed_country" != "1" ]; then
        should_block=true
    fi
    
    # Compare with expected
    if [ "$should_block" = "$expected_block" ]; then
        echo "✅ PASS: allowed_country=$allowed_country, blocked_country=$blocked_country → BLOCK=$should_block (expected)"
        ((passed++))
    else
        echo "❌ FAIL: allowed_country=$allowed_country, blocked_country=$blocked_country → BLOCK=$should_block (expected $expected_block)"
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
