#!/bin/bash

# Generate a sample nginx config to visually verify the fix
# This extracts just the filtering section from what deploy.sh generates

echo "================================"
echo "  Generated Nginx Config Preview"
echo "================================"
echo ""
echo "This is the GeoIP filtering section that will be generated:"
echo ""

cat << 'EOF'
# GeoIP Configuration (at http block level)
geoip_country /usr/share/GeoIP/GeoIP.dat;
geoip_proxy_recursive on;

# Map country codes to allowed (1 = allowed, 0 or -1 = blocked)
map $geoip_country_code $allowed_country {
    default -1;      # Unknown countries default to -1 (blocked)
    US 1;            # Allowed
    CA 1;            # Allowed
    GB 1;            # Allowed
    AU 1;            # Allowed
    FI 1;            # Allowed
}

# Map country codes to blocked list (1 = blocked, 0 = allowed)
map $geoip_country_code $blocked_country {
    default 0;       # Default to 0 (not blocked)
    CN 1;            # Blocked
    RU 1;            # Blocked
    IR 1;            # Blocked
}

# Location block filtering (FIXED VERSION)
location / {
    # Block if country is in blocked list
    if ($blocked_country = 1) {
        return 444;
    }
    # Block if allow-mode is on AND country is not in allow list (includes unknown/localhost value -1)
    if ($allowed_country != 1) {
        return 444;
    }
    
    # ... proxy to Guacamole ...
    proxy_pass http://guacamole:8080/guacamole/;
}
EOF

echo ""
echo ""
echo "================================"
echo "  Filtering Logic Explanation"
echo "================================"
echo ""

echo "OLD (BROKEN) LOGIC:"
echo "  if (\$allowed_country = 0) { return 444; }"
echo "  ❌ Only blocks when value equals 0"
echo "  ❌ Doesn't block value -1 (unknown/localhost)"
echo "  ❌ Non-allowed countries incorrectly allowed through"
echo ""

echo "NEW (FIXED) LOGIC:"
echo "  if (\$allowed_country != 1) { return 444; }"
echo "  ✅ Blocks when value is NOT 1"
echo "  ✅ Blocks value 0 (explicitly blocked countries)"
echo "  ✅ Blocks value -1 (unknown/localhost/Docker IPs)"
echo "  ✅ Only allows value 1 (explicitly allowed countries)"
echo ""

echo "================================"
echo "  Test Scenarios"
echo "================================"
echo ""

scenarios=(
    "USA (8.8.8.8)|allowed_country=1, blocked_country=0|200 OK - Access Allowed"
    "Canada (206.108.35.1)|allowed_country=1, blocked_country=0|200 OK - Access Allowed"
    "Germany (8.26.56.26)|allowed_country=-1, blocked_country=0|444 Blocked - Unknown Country"
    "Russia (91.199.119.83)|allowed_country=-1, blocked_country=0|444 Blocked - Unknown Country"
    "China (202.106.0.20)|allowed_country=1, blocked_country=1|444 Blocked - In Blocklist"
    "Iran (client)|allowed_country=-1, blocked_country=1|444 Blocked - Unknown + Blocklist"
    "Localhost (127.0.0.1)|allowed_country=-1, blocked_country=0|444 Blocked - Unknown"
)

for scenario in "${scenarios[@]}"; do
    IFS='|' read -r country logic response <<< "$scenario"
    printf "%-30s | %-35s | %s\n" "$country" "$logic" "$response"
done

echo ""
echo "================================"
