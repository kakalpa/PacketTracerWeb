#!/bin/bash

echo "=== Testing Automatic Config Regeneration and Restart ==="
echo ""

# Current .env settings
echo "1️⃣ Current .env GEOIP settings:"
grep "GEOIP" .env | head -5
echo ""

# Current nginx config
echo "2️⃣ Current nginx config GeoIP map (first 5 countries):"
docker exec pt-nginx1 cat /etc/nginx/conf.d/ptweb.conf | grep -A 10 "map \$geoip_country_code \$allowed_country" | head -8
echo ""

# Make a test change: Add a new country to GEOIP_ALLOW_COUNTRIES
echo "3️⃣ Making test change: Adding 'DE' (Germany) to allowed countries..."
CURRENT_ALLOWED=$(grep "^GEOIP_ALLOW_COUNTRIES=" .env | cut -d'=' -f2)
NEW_ALLOWED="${CURRENT_ALLOWED},DE"
sed -i "s/^GEOIP_ALLOW_COUNTRIES=.*/GEOIP_ALLOW_COUNTRIES=$NEW_ALLOWED/" .env
echo "   Updated .env: GEOIP_ALLOW_COUNTRIES=$NEW_ALLOWED"
echo ""

# Call the API to apply configuration
echo "4️⃣ Calling /api/env/config to apply changes..."
RESPONSE=$(curl -s -X POST http://localhost:5000/api/env/config \
  -H "Content-Type: application/json" \
  -b "session=test" \
  -d '{
    "https": {"enabled": true, "cert_path": "/etc/ssl/certs/server.crt", "key_path": "/etc/ssl/private/server.key"},
    "geoip": {"allow_enabled": true, "allow_countries": "FI,SL,UK,US,DE", "block_enabled": true, "block_countries": "CN,RU,IR"},
    "rate_limit": {"enabled": true, "rate": "175r/s", "burst": "200"},
    "production": {"mode": false, "public_ip": ""},
    "ssl": {"cert_path": "/etc/ssl/certs/server.crt", "key_path": "/etc/ssl/private/server.key"}
  }')

echo "   Response: $RESPONSE"
echo ""

# Wait for restart
sleep 4

# Check if change is in nginx config
echo "5️⃣ Checking if 'DE' is now in nginx config..."
if docker exec pt-nginx1 cat /etc/nginx/conf.d/ptweb.conf | grep -q "DE.*1"; then
  echo "   ✅ SUCCESS: DE is now in the allowed_country map!"
else
  echo "   ❌ FAILED: DE is NOT in the allowed_country map"
fi
echo ""

# Show the updated map
echo "6️⃣ Updated nginx config GeoIP map:"
docker exec pt-nginx1 cat /etc/nginx/conf.d/ptweb.conf | grep -A 10 "map \$geoip_country_code \$allowed_country" | head -8
echo ""

# Verify .env was updated
echo "7️⃣ Verify .env still has the change:"
grep "GEOIP_ALLOW_COUNTRIES=" .env
echo ""

echo "=== Test Complete ==="
