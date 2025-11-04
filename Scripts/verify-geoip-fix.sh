#!/bin/bash

# Direct test of the fix by checking the deploy.sh source code

echo "================================"
echo "  GeoIP Fix Verification"
echo "================================"
echo ""

DEPLOY_SCRIPT="deploy.sh"

if [ ! -f "$DEPLOY_SCRIPT" ]; then
    echo "❌ $DEPLOY_SCRIPT not found"
    exit 1
fi

echo "Checking deploy.sh for the GeoIP filtering fix..."
echo ""

# Test 1: Check for the NEW (correct) logic
if grep -q 'if (\$allowed_country != 1)' "$DEPLOY_SCRIPT"; then
    echo "✅ PASS: Found FIXED logic: if (\$allowed_country != 1)"
    FIXED_FOUND=1
else
    echo "❌ FAIL: Fixed logic NOT found"
    FIXED_FOUND=0
fi

# Test 2: Verify the OLD (broken) logic is removed
if grep -q 'if (\$allowed_country = 0)' "$DEPLOY_SCRIPT"; then
    echo "❌ FAIL: Old broken logic still present: if (\$allowed_country = 0)"
    OLD_STILL_THERE=1
else
    echo "✅ PASS: Old broken logic removed"
    OLD_STILL_THERE=0
fi

echo ""
echo "Source code verification:"
grep -n "if (\$allowed_country" "$DEPLOY_SCRIPT" | head -5

echo ""
echo "================================"

if [ $FIXED_FOUND -eq 1 ] && [ $OLD_STILL_THERE -eq 0 ]; then
    echo "✅ VERIFICATION PASSED: Fix is correctly applied in deploy.sh"
    exit 0
else
    echo "❌ VERIFICATION FAILED: Fix not properly applied"
    exit 1
fi
