#!/bin/bash

# GeoIP Blocking Test Script
# Simulates traffic from different countries using X-Forwarded-For header

cd "$(dirname "$0")"
WORKDIR="$(pwd)"

# Load .env configuration
if [ -f "$WORKDIR/.env" ]; then
    source "$WORKDIR/.env"
fi

RED='\e[31m'
GREEN='\e[32m'
YELLOW='\e[33m'
BLUE='\e[34m'
NC='\e[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║     GeoIP Blocking Simulation Test                    ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get GeoIP database info
echo -e "${YELLOW}GeoIP Database Information:${NC}"
docker exec pt-nginx1 bash -c 'ls -lh /usr/share/GeoIP/*.dat' | awk '{print "  " $9 " (" $5 ")"}'
echo ""

# Current configuration
echo -e "${YELLOW}Current Configuration:${NC}"
echo "  NGINX_GEOIP_ALLOW: ${NGINX_GEOIP_ALLOW:-false}"
echo "  GEOIP_ALLOW_COUNTRIES: ${GEOIP_ALLOW_COUNTRIES}"
echo "  NGINX_GEOIP_BLOCK: ${NGINX_GEOIP_BLOCK:-false}"
echo "  GEOIP_BLOCK_COUNTRIES: ${GEOIP_BLOCK_COUNTRIES}"
echo ""

# Map of country codes to sample IPs (from GeoIP database)
declare -A COUNTRY_IPS=(
    # Allowed countries
    ["US"]="8.8.8.8"              # USA - Google DNS
    ["CA"]="1.1.1.1"              # Canada (approximately)
    ["GB"]="2.125.160.1"          # UK
    ["AU"]="1.128.0.1"            # Australia
    ["FI"]="80.191.36.1"          # Finland
    
    # Blocked countries
    ["CN"]="1.0.0.1"              # China
    ["RU"]="5.8.0.1"              # Russia
    ["IR"]="2.144.0.1"            # Iran
    
    # Other countries
    ["DE"]="3.8.0.1"              # Germany
    ["JP"]="1.160.0.1"            # Japan
    ["BR"]="177.0.0.1"            # Brazil
)

# Function to test traffic from a country
test_country() {
    local country=$1
    local ip=$2
    local description=$3
    
    echo -n "Testing from ${country} (${description}): "
    
    # Make request with X-Forwarded-For header to simulate the IP
    # Note: nginx needs geoip_proxy_recursive on to read X-Forwarded-For
    response=$(curl -s -w "\n%{http_code}" \
        -H "X-Forwarded-For: $ip" \
        -H "X-Real-IP: $ip" \
        http://localhost/ 2>&1)
    
    http_code=$(echo "$response" | tail -1)
    body=$(echo "$response" | head -1)
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✅ ALLOWED (HTTP $http_code)${NC}"
        return 0
    elif [ "$http_code" = "444" ] || [ "$http_code" = "000" ]; then
        echo -e "${RED}❌ BLOCKED (HTTP $http_code)${NC}"
        return 1
    else
        echo -e "${YELLOW}⚠️  UNKNOWN (HTTP $http_code)${NC}"
        return 0
    fi
}

# Test allowed countries
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}Testing ALLOWED Countries (should all return HTTP 200)${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

allowed_passed=0
allowed_total=0

for country in US CA GB AU FI; do
    ((allowed_total++))
    if test_country "$country" "${COUNTRY_IPS[$country]}" "Allowed country"; then
        ((allowed_passed++))
    fi
done

echo ""

# Test blocked countries
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${RED}Testing BLOCKED Countries (should all return HTTP 444/000)${NC}"
echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

blocked_passed=0
blocked_total=0

for country in CN RU IR; do
    ((blocked_total++))
    # For blocked countries, we expect failure (444 or connection reset)
    echo -n "Testing from ${country}: "
    
    response=$(curl -s -w "\n%{http_code}" \
        -H "X-Forwarded-For: ${COUNTRY_IPS[$country]}" \
        -H "X-Real-IP: ${COUNTRY_IPS[$country]}" \
        http://localhost/ 2>&1)
    
    http_code=$(echo "$response" | tail -1)
    
    if [ "$http_code" = "444" ] || [ "$http_code" = "000" ] || [ -z "$http_code" ]; then
        echo -e "${GREEN}✅ BLOCKED (HTTP $http_code)${NC}"
        ((blocked_passed++))
    elif [ "$http_code" = "200" ]; then
        echo -e "${YELLOW}⚠️  ALLOWED (HTTP $http_code) - Blocking not enforced${NC}"
    else
        echo -e "${YELLOW}⚠️  UNKNOWN (HTTP $http_code)${NC}"
    fi
done

echo ""

# Test other countries
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}Testing OTHER Countries (behavior depends on mode)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

for country in DE JP BR; do
    test_country "$country" "${COUNTRY_IPS[$country]}" "Other country" || true
done

echo ""

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}SUMMARY${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

echo "Allowed Countries: $allowed_passed/$allowed_total passed"
echo "Blocked Countries: $blocked_passed/$blocked_total passed"
echo ""

if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ]; then
    echo -e "${YELLOW}ℹ️  Note: GeoIP blocking framework is configured but may not be${NC}"
    echo -e "${YELLOW}   actively enforced in ptweb.conf yet.${NC}"
    echo ""
    echo -e "${YELLOW}To enable active blocking, uncomment the if-block in ptweb.conf.${NC}"
else
    echo -e "${YELLOW}ℹ️  GeoIP filtering is not enabled in .env${NC}"
fi

echo ""
echo -e "${GREEN}Test complete!${NC}"
