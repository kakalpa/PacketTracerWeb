#!/bin/bash

# Extract and test the actual nginx config generation from deploy.sh

echo "================================"
echo "  Deploy.sh Config Generation Test"
echo "================================"
echo ""

# Create a temporary test to generate just the nginx config
TEMP_FILE=$(mktemp)

# Extract the generate_nginx_config function and test it
bash -c '
source deploy.sh 2>/dev/null

# Call the function
generate_nginx_config "172.17.0.6" "false" "" "" 
' > "$TEMP_FILE" 2>/dev/null

if [ -s "$TEMP_FILE" ]; then
    echo "✅ Config generation successful!"
    echo ""
    echo "Checking for key lines in generated config:"
    echo ""
    
    # Check for the FIXED filtering logic
    if grep -q 'if (\$allowed_country != 1)' "$TEMP_FILE"; then
        echo "✅ PASS: Found fixed logic: if (\$allowed_country != 1)"
    else
        echo "❌ FAIL: Did not find fixed logic"
        grep -n "if.*allowed_country" "$TEMP_FILE" || echo "No allowed_country filtering found"
    fi
    
    # Check for blocked country filtering
    if grep -q 'if (\$blocked_country = 1)' "$TEMP_FILE"; then
        echo "✅ PASS: Found blocked country logic: if (\$blocked_country = 1)"
    else
        echo "❌ FAIL: Did not find blocked country logic"
    fi
    
    # Check for GeoIP directives
    if grep -q 'geoip_country' "$TEMP_FILE"; then
        echo "✅ PASS: GeoIP configuration present"
    else
        echo "❌ FAIL: GeoIP configuration missing"
    fi
    
    # Check for X-Forwarded-For handling
    if grep -q 'X-Forwarded-For' "$TEMP_FILE"; then
        echo "✅ PASS: X-Forwarded-For proxy header configured"
    else
        echo "❌ FAIL: X-Forwarded-For not configured"
    fi
    
    echo ""
    echo "================================"
    echo "  Generated Location Block"
    echo "================================"
    echo ""
    
    # Extract and display the location block
    sed -n '/location \//,/^    }/p' "$TEMP_FILE" | head -30
    
else
    echo "❌ Failed to generate config"
fi

rm -f "$TEMP_FILE"

echo ""
echo "================================"
echo "✅ Local testing complete!"
echo "================================"
