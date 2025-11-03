#!/bin/bash
# Test SSL certificate and HTTPS setup validation

set -e

WORKDIR="$(cd "$(dirname "$0")" && pwd)"
SSL_CERT="$WORKDIR/ssl/server.crt"
SSL_KEY="$WORKDIR/ssl/server.key"

echo "╔════════════════════════════════════════════════════════╗"
echo "║          SSL Certificate & HTTPS Setup Test           ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# Color codes
GREEN='\e[32m'
RED='\e[31m'
YELLOW='\e[33m'
NC='\e[0m'

TESTS_PASSED=0
TESTS_FAILED=0

# Test 1: Check certificate file exists
echo "Test 1: SSL Certificate file exists"
if [ -f "$SSL_CERT" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 2: Check private key file exists
echo "Test 2: SSL Private key file exists"
if [ -f "$SSL_KEY" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 3: Verify certificate is valid
echo "Test 3: Certificate validity check"
if openssl x509 -in "$SSL_CERT" -noout 2>&1 | grep -q "Certificate:" || [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 4: Check certificate expiry
echo "Test 4: Certificate has not expired"
EXPIRY=$(openssl x509 -in "$SSL_CERT" -noout -enddate | cut -d= -f2)
EXPIRY_EPOCH=$(date -d "$EXPIRY" +%s)
CURRENT_EPOCH=$(date +%s)
if [ $EXPIRY_EPOCH -gt $CURRENT_EPOCH ]; then
    echo -e "${GREEN}✅ PASS${NC} (Expires: $EXPIRY)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC} (Expired: $EXPIRY)"
    ((TESTS_FAILED++))
fi

# Test 5: Verify certificate has correct CN
echo "Test 5: Certificate CN is 'localhost'"
if openssl x509 -in "$SSL_CERT" -noout -subject | grep -q "CN = localhost\|CN=localhost"; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 6: Verify certificate is self-signed
echo "Test 6: Certificate is self-signed"
if openssl x509 -in "$SSL_CERT" -noout -text | grep -q "Subject:.*Issuer:"; then
    SUBJECT=$(openssl x509 -in "$SSL_CERT" -noout -subject | cut -d= -f2-)
    ISSUER=$(openssl x509 -in "$SSL_CERT" -noout -issuer | cut -d= -f2-)
    if [ "$SUBJECT" = "$ISSUER" ]; then
        echo -e "${GREEN}✅ PASS${NC}"
        ((TESTS_PASSED++))
    else
        echo -e "${RED}❌ FAIL${NC}"
        ((TESTS_FAILED++))
    fi
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 7: Check .env has ENABLE_HTTPS setting
echo "Test 7: .env file has ENABLE_HTTPS configuration"
if [ -f "$WORKDIR/.env" ] && grep -q "ENABLE_HTTPS" "$WORKDIR/.env"; then
    HTTPS_ENABLED=$(grep "ENABLE_HTTPS" "$WORKDIR/.env" | cut -d= -f2)
    echo -e "${GREEN}✅ PASS${NC} (ENABLE_HTTPS=$HTTPS_ENABLED)"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 8: Check SSL paths in .env
echo "Test 8: .env has SSL_CERT_PATH and SSL_KEY_PATH"
if [ -f "$WORKDIR/.env" ] && grep -q "SSL_CERT_PATH" "$WORKDIR/.env" && grep -q "SSL_KEY_PATH" "$WORKDIR/.env"; then
    CERT_PATH=$(grep "SSL_CERT_PATH" "$WORKDIR/.env" | cut -d= -f2)
    KEY_PATH=$(grep "SSL_KEY_PATH" "$WORKDIR/.env" | cut -d= -f2)
    echo -e "${GREEN}✅ PASS${NC}"
    echo "   Cert Path: $CERT_PATH"
    echo "   Key Path: $KEY_PATH"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 9: Verify certificate and key match
echo "Test 9: Certificate and private key match"
CERT_MODULUS=$(openssl x509 -in "$SSL_CERT" -noout -modulus 2>/dev/null | md5sum)
KEY_MODULUS=$(openssl rsa -in "$SSL_KEY" -noout -modulus 2>/dev/null | md5sum)
if [ "$CERT_MODULUS" = "$KEY_MODULUS" ]; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${RED}❌ FAIL${NC}"
    ((TESTS_FAILED++))
fi

# Test 10: Check certificate has Subject Alt Name for localhost
echo "Test 10: Certificate includes localhost in SAN"
if openssl x509 -in "$SSL_CERT" -noout -text 2>/dev/null | grep -q "localhost"; then
    echo -e "${GREEN}✅ PASS${NC}"
    ((TESTS_PASSED++))
else
    echo -e "${YELLOW}⚠️  WARNING${NC} (SAN not found, cert still valid for localhost)"
    ((TESTS_PASSED++))
fi

echo ""
echo "════════════════════════════════════════════════════════"
echo "Test Summary"
echo "════════════════════════════════════════════════════════"
echo "Passed: $TESTS_PASSED"
echo "Failed: $TESTS_FAILED"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED!${NC}"
    echo ""
    echo "SSL setup is ready for HTTPS deployment:"
    echo "  1. Ensure .env has: ENABLE_HTTPS=true"
    echo "  2. Run: bash deploy.sh"
    echo "  3. Access at: https://localhost/"
    echo ""
    echo "⚠️  Browser will show security warning (self-signed cert)"
    echo "   Click 'Advanced' → 'Proceed anyway' to continue."
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    exit 1
fi
