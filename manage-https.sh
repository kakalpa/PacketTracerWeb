#!/bin/bash
# Enable or disable HTTPS for management console
# Usage: bash manage-https.sh [enable|disable|status]

set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"

usage() {
    cat <<EOF
Management Console HTTPS Configuration

Usage: bash manage-https.sh [enable|disable|status]

Commands:
  enable       - Enable HTTPS for management console (requires SSL certificates)
  disable      - Disable HTTPS, use HTTP only
  status       - Show current HTTPS status
  
Examples:
  # Enable HTTPS
  bash manage-https.sh enable
  
  # Disable HTTPS
  bash manage-https.sh disable
  
  # Check status
  bash manage-https.sh status

Note: HTTPS requires SSL certificates at ./ssl/server.crt and ./ssl/server.key
To generate self-signed certificates, run:
  bash generate-ssl-cert.sh

EOF
}

if [[ $# -lt 1 ]]; then
    usage
    exit 1
fi

case "$1" in
    enable)
        echo "=== Enabling HTTPS for Management Console ==="
        
        # Check if certificates exist
        if [ ! -f "$WORKDIR/ssl/server.crt" ] || [ ! -f "$WORKDIR/ssl/server.key" ]; then
            echo "ERROR: SSL certificates not found!"
            echo "Required files:"
            echo "  - $WORKDIR/ssl/server.crt"
            echo "  - $WORKDIR/ssl/server.key"
            echo ""
            echo "To generate self-signed certificates, run:"
            echo "  bash generate-ssl-cert.sh"
            exit 1
        fi
        
        # Update .env
        if grep -q "^ENABLE_HTTPS=" ".env" 2>/dev/null; then
            sed -i 's/^ENABLE_HTTPS=.*/ENABLE_HTTPS=true/' "$WORKDIR/.env"
        else
            echo "ENABLE_HTTPS=true" >> "$WORKDIR/.env"
        fi
        
        echo "✓ HTTPS enabled in .env"
        echo ""
        echo "Next steps:"
        echo "  1. Rebuild pt-management image: docker build -t pt-management:latest pt-management/"
        echo "  2. Restart pt-management container:"
        echo "     docker rm -f pt-management 2>/dev/null || true"
        echo "     docker run -d --name pt-management ..."
        echo ""
        echo "Or for full redeployment:"
        echo "  bash deploy-full.sh recreate"
        ;;
        
    disable)
        echo "=== Disabling HTTPS for Management Console ==="
        
        # Update .env
        if grep -q "^ENABLE_HTTPS=" "$WORKDIR/.env" 2>/dev/null; then
            sed -i 's/^ENABLE_HTTPS=.*/ENABLE_HTTPS=false/' "$WORKDIR/.env"
        else
            echo "ENABLE_HTTPS=false" >> "$WORKDIR/.env"
        fi
        
        echo "✓ HTTPS disabled in .env"
        echo ""
        echo "Management console will run on HTTP (port 5000)"
        echo "To apply changes, restart the container:"
        echo "  docker rm -f pt-management 2>/dev/null || true"
        echo "  bash deploy-full.sh"
        ;;
        
    status)
        echo "=== Management Console HTTPS Status ==="
        
        # Check .env
        if [ -f "$WORKDIR/.env" ]; then
            HTTPS_ENABLED=$(grep "^ENABLE_HTTPS=" "$WORKDIR/.env" | cut -d= -f2 || echo "not set")
            echo "Configuration (.env): $HTTPS_ENABLED"
        else
            echo "Configuration (.env): not found"
        fi
        
        # Check certificates
        if [ -f "$WORKDIR/ssl/server.crt" ] && [ -f "$WORKDIR/ssl/server.key" ]; then
            echo "SSL Certificates: ✓ Present"
            
            # Show cert info
            echo ""
            echo "Certificate Info:"
            openssl x509 -in "$WORKDIR/ssl/server.crt" -noout -subject -dates 2>/dev/null || echo "  (Could not read certificate)"
        else
            echo "SSL Certificates: ✗ Missing"
        fi
        
        # Check container status
        echo ""
        if docker ps --format '{{.Names}}' | grep -q '^pt-management$'; then
            echo "Container Status: ✓ Running"
            
            # Check which port is listening
            PORT=$(docker port pt-management 2>/dev/null | grep -oP '5\d{3}' | sort | uniq || echo "unknown")
            echo "Listening on port(s): $PORT"
        else
            echo "Container Status: ✗ Not running"
        fi
        ;;
        
    *)
        echo "Unknown command: $1"
        usage
        exit 1
        ;;
esac

exit 0
