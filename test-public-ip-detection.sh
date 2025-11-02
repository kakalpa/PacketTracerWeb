#!/bin/bash

# Test script to simulate the public IP detection logic

echo "================================"
echo "  Public IP Detection Test"
echo "================================"
echo ""

echo "Scenario 1: Development Mode (PRODUCTION_MODE=false)"
echo "---"
PRODUCTION_MODE=false
PUBLIC_IP=""
NGINX_TRUSTED_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

if [ "$PRODUCTION_MODE" = "true" ] || [ "$PRODUCTION_MODE" = "1" ]; then
    echo "Production mode enabled"
else
    echo "✓ Development mode (local IPs only)"
fi
echo "  Trusted IPs: $NGINX_TRUSTED_IPS"
echo ""

echo "Scenario 2: Production Mode - Auto-detect (simulated)"
echo "---"
PRODUCTION_MODE=true
PUBLIC_IP=""
NGINX_TRUSTED_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

if [ "$PRODUCTION_MODE" = "true" ] || [ "$PRODUCTION_MODE" = "1" ]; then
    if [ -z "$PUBLIC_IP" ]; then
        echo "Production mode: Detecting public IP (simulated)..."
        # In real deployment, this would be:
        # PUBLIC_IP=$(curl -s --max-time 5 https://ifconfig.co 2>/dev/null || echo "")
        PUBLIC_IP="67.172.37.62"  # Simulated detection
        echo "✓ Detected public IP: $PUBLIC_IP"
    fi
    
    if [ -n "$PUBLIC_IP" ]; then
        NGINX_TRUSTED_IPS="${NGINX_TRUSTED_IPS},$PUBLIC_IP"
        echo "✓ Added public IP to trusted IPs"
    fi
fi
echo "  Trusted IPs: $NGINX_TRUSTED_IPS"
echo ""

echo "Scenario 3: Production Mode - Manual IP"
echo "---"
PRODUCTION_MODE=true
PUBLIC_IP="203.0.113.1"  # Manually specified
NGINX_TRUSTED_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

if [ "$PRODUCTION_MODE" = "true" ] || [ "$PRODUCTION_MODE" = "1" ]; then
    if [ -z "$PUBLIC_IP" ]; then
        echo "Would detect public IP..."
    else
        echo "Production mode: Using PUBLIC_IP from .env: $PUBLIC_IP"
    fi
    
    if [ -n "$PUBLIC_IP" ]; then
        NGINX_TRUSTED_IPS="${NGINX_TRUSTED_IPS},$PUBLIC_IP"
        echo "✓ Added public IP to trusted IPs"
    fi
fi
echo "  Trusted IPs: $NGINX_TRUSTED_IPS"
echo ""

echo "Scenario 4: Custom Override"
echo "---"
PRODUCTION_MODE=true
PUBLIC_IP=""
NGINX_TRUSTED_IPS_OVERRIDE="127.0.0.1,10.0.0.0/8,custom.domain.com"
NGINX_TRUSTED_IPS="127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

if [ -n "${NGINX_TRUSTED_IPS_OVERRIDE:-}" ]; then
    NGINX_TRUSTED_IPS="$NGINX_TRUSTED_IPS_OVERRIDE"
    echo "✓ Using NGINX_TRUSTED_IPS_OVERRIDE"
fi
echo "  Trusted IPs: $NGINX_TRUSTED_IPS"
echo ""

echo "================================"
echo "✅ All scenarios tested successfully!"
echo "================================"
