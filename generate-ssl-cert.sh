#!/bin/bash
# Generate self-signed SSL certificate for local HTTPS testing
# Usage: bash generate-ssl-cert.sh
# Creates: ssl/server.crt and ssl/server.key

set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
SSL_DIR="$WORKDIR/ssl"
CERT_FILE="$SSL_DIR/server.crt"
KEY_FILE="$SSL_DIR/server.key"

echo "🔐 Generating self-signed SSL certificate for local testing..."
echo ""

# Create ssl directory if it doesn't exist
mkdir -p "$SSL_DIR"

# Check if certificate already exists
if [ -f "$CERT_FILE" ] && [ -f "$KEY_FILE" ]; then
    echo "⚠️  Certificate already exists:"
    echo "   - $CERT_FILE"
    echo "   - $KEY_FILE"
    echo ""
    read -p "Do you want to regenerate? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing certificate."
        exit 0
    fi
fi

# Generate self-signed certificate
echo "📝 Creating certificate for: localhost"
echo "   Valid for: 365 days"
echo ""

openssl req -x509 \
    -newkey rsa:2048 \
    -keyout "$KEY_FILE" \
    -out "$CERT_FILE" \
    -days 365 \
    -nodes \
    -subj "/CN=localhost/O=Local Testing/C=US" \
    -addext "subjectAltName=DNS:localhost,DNS:*.localhost,IP:127.0.0.1"

echo "✅ Certificate generated successfully!"
echo ""
echo "📁 Files:"
echo "   Certificate: $CERT_FILE"
echo "   Private Key: $KEY_FILE"
echo ""
echo "🚀 To use with HTTPS:"
echo "   1. Enable in .env:"
echo "      ENABLE_HTTPS=true"
echo "      SSL_CERT_PATH=/etc/ssl/certs/server.crt"
echo "      SSL_KEY_PATH=/etc/ssl/private/server.key"
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
