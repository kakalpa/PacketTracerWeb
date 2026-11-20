#!/bin/bash
# Generate self-signed SSL certificate for local HTTPS testing
# Usage: bash generate-ssl-cert.sh [--if-missing] [--non-interactive]
# Creates: ssl/server.crt (0644) and ssl/server.key (0600)

set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
SSL_DIR="$WORKDIR/ssl"
CERT_FILE="$SSL_DIR/server.crt"
KEY_FILE="$SSL_DIR/server.key"

IF_MISSING=false
NONINTERACTIVE="${NONINTERACTIVE:-false}"

while [ $# -gt 0 ]; do
    case "$1" in
        --if-missing)
            IF_MISSING=true
            ;;
        --non-interactive)
            NONINTERACTIVE=true
            ;;
        -h|--help)
            echo "Usage: bash generate-ssl-cert.sh [--if-missing] [--non-interactive]"
            exit 0
            ;;
        *)
            echo "ERROR: Unknown option: $1" >&2
            echo "Usage: bash generate-ssl-cert.sh [--if-missing] [--non-interactive]" >&2
            exit 1
            ;;
    esac
    shift
done

echo "🔐 Generating self-signed SSL certificate for local testing..."
echo ""

# Create ssl directory if it doesn't exist
mkdir -p "$SSL_DIR"

# Check if certificate already exists
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    chmod 600 "$KEY_FILE"
    chmod 644 "$CERT_FILE"
    if [ "$IF_MISSING" = "true" ]; then
        echo "✓ Existing SSL certificate found; keeping $CERT_FILE and $KEY_FILE (permissions hardened)."
        exit 0
    fi
    echo "⚠️  Certificate already exists:"
    echo "   - $CERT_FILE"
    echo "   - $KEY_FILE"
    echo ""
    if [ "$NONINTERACTIVE" = "true" ] || [ "$NONINTERACTIVE" = "1" ]; then
        echo "ℹ️  Non-interactive mode enabled: regenerating existing certificate..."
    else
        read -p "Do you want to regenerate? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Keeping existing certificate."
            exit 0
        fi
    fi
fi

# Generate self-signed certificate with restrictive umask for private key
echo "📝 Creating certificate for: localhost"
echo "   Valid for: 365 days"
echo ""

(
    umask 077
    openssl req -x509 \
        -newkey rsa:2048 \
        -keyout "$KEY_FILE" \
        -out "$CERT_FILE" \
        -days 365 \
        -nodes \
        -subj "/CN=localhost/O=Local Testing/C=US" \
        -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"
)
chmod 600 "$KEY_FILE"
chmod 644 "$CERT_FILE"

echo "✅ Certificate generated successfully!"
echo ""
echo "📁 Files:"
echo "   Certificate: $CERT_FILE (0644)"
echo "   Private Key: $KEY_FILE (0600)"
echo ""
echo "🚀 To use with HTTPS:"
echo "   1. Enable in .env:"
echo "      TLS_MODE=self-signed"
echo "      ENABLE_HTTPS=true"
echo "      SSL_CERT_PATH=/etc/ssl/ptweb/server.crt"
echo "      SSL_KEY_PATH=/etc/ssl/ptweb/server.key"
echo ""
echo "   2. Run deployment:"
echo "      bash deploy.sh"
echo ""
echo "⚠️  Browser Warning:"
echo "   Your browser will show a security warning because the cert is self-signed."
echo "   This is expected for local testing. Click 'Advanced' → 'Proceed anyway'."
echo ""
echo "🔍 Verify certificate:"
echo "   openssl x509 -in $CERT_FILE -text -noout"
echo ""
