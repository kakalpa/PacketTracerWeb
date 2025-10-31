#!/bin/bash

# Secure Setup Script for PacketTracerWeb
# Generates strong random credentials and configures the deployment securely
# Features: Random credentials, HTTPS/TLS, GeoIP restrictions, Download authentication
# Usage: bash secure-setup.sh
# Non-interactive: NONINTERACTIVE=1 bash secure-setup.sh

set -e

# Check if we're in non-interactive mode
NONINTERACTIVE="${NONINTERACTIVE:-0}"

echo -e "\e[32m=== PacketTracerWeb Secure Setup ===\e[0m"
echo ""
if [[ "$NONINTERACTIVE" == "1" ]]; then
    echo "Running in non-interactive mode (defaults: no HTTPS, no GeoIP, no download auth)"
else
    echo "⚠️  This script will generate new credentials and configure your deployment for production."
    echo "Make sure to save the credentials in a secure location!"
fi
echo ""

# Check if credentials already exist
if [[ -f ".env.secure" ]]; then
    echo -e "\e[33m⚠️  .env.secure already exists!\e[0m"
    if [[ "$NONINTERACTIVE" != "1" ]]; then
        printf "Do you want to regenerate credentials? (y/n) "
        read -r REGENERATE
        if [[ ! $REGENERATE =~ ^[Yy]$ ]]; then
            echo "Skipping credential generation."
            exit 0
        fi
    else
        echo "Backing up and regenerating..."
    fi
    echo "Backing up existing credentials to .env.secure.backup"
    cp .env.secure .env.secure.backup
fi

echo -e "\e[32m--- Generating Secure Credentials ---\e[0m"

# Generate strong random passwords
DB_ROOT_PASSWORD=$(openssl rand -base64 32)
DB_USER_PASSWORD=$(openssl rand -base64 32)
VNC_PASSWORD=$(openssl rand -base64 24)
GUACAMOLE_PASSWORD=$(openssl rand -base64 16)
DOWNLOAD_AUTH_USER="downloader"
DOWNLOAD_AUTH_PASSWORD=$(openssl rand -base64 16)
DB_NAME="guacamole_db"
DB_USER="ptdbuser"

echo "✓ Generated MariaDB root password (32 bytes)"
echo "✓ Generated MariaDB user password (32 bytes)"
echo "✓ Generated VNC password (24 bytes)"
echo "✓ Generated Guacamole user password (16 bytes)"
echo "✓ Generated Download authentication credentials"
echo ""

# ===== HTTPS/TLS CONFIGURATION =====
echo -e "\e[32m--- HTTPS/TLS Configuration ---\e[0m"
if [[ "$NONINTERACTIVE" == "1" ]]; then
    ENABLE_HTTPS_CHOICE="n"
    echo "HTTPS: DISABLED (non-interactive mode, use default)"
else
    printf "Enable HTTPS/TLS? (y/n) [default: n]: "
    read -r ENABLE_HTTPS_CHOICE
fi
ENABLE_HTTPS_CHOICE=${ENABLE_HTTPS_CHOICE:-n}
echo

if [[ $ENABLE_HTTPS_CHOICE =~ ^[Yy]$ ]]; then
    ENABLE_HTTPS="true"
    echo "HTTPS will be enabled."
    printf "Do you have Let's Encrypt certificates ready? (y/n) [default: n]: "
    read -r CERTS_READY
    echo
    if [[ ! $CERTS_READY =~ ^[Yy]$ ]]; then
        echo ""
        echo "📌 To generate self-signed certificates, run:"
        echo "   mkdir -p ptweb-vnc/certs"
        echo "   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \\"
        echo "     -keyout ptweb-vnc/certs/privkey.pem \\"
        echo "     -out ptweb-vnc/certs/fullchain.pem"
        echo ""
        echo "📌 For Let's Encrypt:"
        echo "   sudo certbot certonly --standalone -d your-domain.com"
        echo "   sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ptweb-vnc/certs/"
        echo "   sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ptweb-vnc/certs/"
        echo ""
        printf "Press enter after copying certificates..."
        read -r
    fi
else
    ENABLE_HTTPS="false"
    echo "HTTPS will be DISABLED - HTTP only (not recommended for production)"
fi
echo ""

# ===== GEOIP RESTRICTIONS =====
echo -e "\e[32m--- GeoIP Restrictions ---\e[0m"
if [[ "$NONINTERACTIVE" == "1" ]]; then
    ENABLE_GEOIP_CHOICE="n"
    echo "GeoIP: DISABLED (non-interactive mode, use default)"
else
    printf "Enable GeoIP-based access restrictions? (y/n) [default: n]: "
    read -r ENABLE_GEOIP_CHOICE
fi
ENABLE_GEOIP_CHOICE=${ENABLE_GEOIP_CHOICE:-n}
echo

ALLOWED_COUNTRIES=""
if [[ $ENABLE_GEOIP_CHOICE =~ ^[Yy]$ ]]; then
    ENABLE_GEOIP="true"
    echo "📌 GeoIP allows access only from specific countries"
    echo "   Common codes: US (USA), GB (UK), DE (Germany), CA (Canada), AU (Australia)"
    echo "   See: https://www.iso.org/obp/ui/#search"
    echo ""
    printf "Enter allowed country codes (comma-separated, or press enter for all): "
    read -r ALLOWED_COUNTRIES
    
    if [[ -z "$ALLOWED_COUNTRIES" ]]; then
        echo "No countries specified - will allow access from ALL countries"
        ENABLE_GEOIP="false"
    else
        # Convert to uppercase and validate format
        ALLOWED_COUNTRIES=$(echo "$ALLOWED_COUNTRIES" | tr '[:lower:]' '[:upper:]' | sed 's/[[:space:]]//g')
        echo "Allowed countries: $ALLOWED_COUNTRIES"
    fi
else
    ENABLE_GEOIP="false"
    echo "GeoIP restrictions DISABLED - access allowed from all countries"
fi
echo ""

# ===== DOWNLOAD AUTHENTICATION =====
echo -e "\e[32m--- Download Access Authentication ---\e[0m"
if [[ "$NONINTERACTIVE" == "1" ]]; then
    DOWNLOADS_AUTH_CHOICE="n"
    echo "Download Auth: DISABLED (non-interactive mode, use default)"
else
    printf "Require authentication for /downloads path? (y/n) [default: y]: "
    read -r DOWNLOADS_AUTH_CHOICE
fi
DOWNLOADS_AUTH_CHOICE=${DOWNLOADS_AUTH_CHOICE:-y}
echo

if [[ $DOWNLOADS_AUTH_CHOICE =~ ^[Yy]$ ]]; then
    REQUIRE_DOWNLOAD_AUTH="true"
    echo "✓ Downloads will require HTTP Basic Authentication"
    echo "   Username: $DOWNLOAD_AUTH_USER"
    echo "   Password: (will be shown at end)"
else
    REQUIRE_DOWNLOAD_AUTH="false"
    echo "Downloads will be OPEN to anyone who can access the web UI"
fi
echo ""

# Create .env.secure file
cat > .env.secure << EOF
# PacketTracerWeb Secure Credentials
# Generated: $(date)
# KEEP THIS FILE SAFE - Contains sensitive production credentials!

# MariaDB Configuration
DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}"
DB_NAME="${DB_NAME}"
DB_USER="${DB_USER}"
DB_USER_PASSWORD="${DB_USER_PASSWORD}"
DB_PORT=3306

# VNC Configuration (for Packet Tracer containers)
VNC_PASSWORD="${VNC_PASSWORD}"
VNC_RESOLUTION="1024x768"

# Guacamole Web UI Configuration
GUACAMOLE_USERNAME="ptadmin"
GUACAMOLE_PASSWORD="${GUACAMOLE_PASSWORD}"

# Network Configuration
NGINX_PORT=80
NGINX_SSL_PORT=443
GUACAMOLE_PORT=8080

# Security Settings
ENABLE_HTTPS=${ENABLE_HTTPS}
ENABLE_RATE_LIMITING=true
SESSION_TIMEOUT=3600

# HTTPS/TLS Configuration
SSL_CERT_PATH="./ptweb-vnc/certs/fullchain.pem"
SSL_KEY_PATH="./ptweb-vnc/certs/privkey.pem"

# GeoIP Configuration
ENABLE_GEOIP=${ENABLE_GEOIP}
ALLOWED_COUNTRIES="${ALLOWED_COUNTRIES}"

# Download Authentication
REQUIRE_DOWNLOAD_AUTH=${REQUIRE_DOWNLOAD_AUTH}
DOWNLOAD_AUTH_USER="${DOWNLOAD_AUTH_USER}"
DOWNLOAD_AUTH_PASSWORD="${DOWNLOAD_AUTH_PASSWORD}"

# Backup timestamp
BACKUP_DATE=$(date +%s)
EOF

chmod 600 .env.secure
echo -e "\e[32m✓ Created .env.secure with restricted permissions (600)\e[0m"
echo ""

# Display credentials (ONE TIME ONLY)
echo -e "\e[33m=== IMPORTANT: SAVE THESE CREDENTIALS SECURELY ===\e[0m"
echo ""
echo "📌 Database Configuration:"
echo "   Root Password:  $DB_ROOT_PASSWORD"
echo "   DB User:        $DB_USER"
echo "   DB Password:    $DB_USER_PASSWORD"
echo "   Database:       $DB_NAME"
echo ""
echo "📌 Guacamole Web UI:"
echo "   Username:       ptadmin"
echo "   Password:       $GUACAMOLE_PASSWORD"
echo "   URL:            $(if [[ "$ENABLE_HTTPS" == "true" ]]; then echo "https://"; else echo "http://"; fi)localhost/"
echo ""
echo "📌 VNC (Packet Tracer):"
echo "   Password:       $VNC_PASSWORD"
echo ""
if [[ "$REQUIRE_DOWNLOAD_AUTH" == "true" ]]; then
    echo "📌 Download Authentication:"
    echo "   Username:       $DOWNLOAD_AUTH_USER"
    echo "   Password:       $DOWNLOAD_AUTH_PASSWORD"
    echo ""
fi
echo "📌 Security Features:"
echo "   HTTPS Enabled:           $ENABLE_HTTPS"
echo "   GeoIP Restrictions:      $ENABLE_GEOIP"
if [[ -n "$ALLOWED_COUNTRIES" ]]; then
    echo "   Allowed Countries:       $ALLOWED_COUNTRIES"
fi
echo "   Download Auth Required:  $REQUIRE_DOWNLOAD_AUTH"
echo ""
echo -e "\e[33m⚠️  These credentials are displayed only once. Store them securely!\e[0m"
echo ""

# Ask user to acknowledge (skip in automated mode if NONINTERACTIVE set)
if [[ -z "${NONINTERACTIVE:-}" ]]; then
    printf "I have saved these credentials securely (y/n): "
    read -n 1 -r REPLY
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "\e[31m❌ Setup cancelled. Please save credentials before proceeding.\e[0m"
        exit 1
    fi
else
    echo "✓ Running in non-interactive mode (NONINTERACTIVE=1)"
fi

echo ""
echo -e "\e[32m--- Updating Configuration Files ---\e[0m"

# Update docker-compose.yml with new credentials (using | as delimiter to avoid issues with special chars)
sed -i.bak "s|MARIADB_PASSWORD: 'ptdbpass'|MARIADB_PASSWORD: '${DB_USER_PASSWORD}'|g" ptweb-vnc/docker-compose.yml
sed -i "s|MYSQL_PASSWORD: 'ptdbpass'|MYSQL_PASSWORD: '${DB_USER_PASSWORD}'|g" ptweb-vnc/docker-compose.yml
sed -i "s|MARIADB_USER: 'ptdbuser'|MARIADB_USER: '${DB_USER}'|g" ptweb-vnc/docker-compose.yml
sed -i "s|MYSQL_USER: 'ptdbuser'|MYSQL_USER: '${DB_USER}'|g" ptweb-vnc/docker-compose.yml

echo "✓ Updated docker-compose.yml"

# Create initialization script for deploy.sh to use
cat > .env.init << EOF
# Auto-loaded by deploy.sh
export DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD}"
export DB_USER_PASSWORD="${DB_USER_PASSWORD}"
export VNC_PASSWORD="${VNC_PASSWORD}"
export GUACAMOLE_PASSWORD="${GUACAMOLE_PASSWORD}"
export ENABLE_HTTPS="${ENABLE_HTTPS}"
export ENABLE_GEOIP="${ENABLE_GEOIP}"
export ALLOWED_COUNTRIES="${ALLOWED_COUNTRIES}"
export REQUIRE_DOWNLOAD_AUTH="${REQUIRE_DOWNLOAD_AUTH}"
export DOWNLOAD_AUTH_USER="${DOWNLOAD_AUTH_USER}"
export DOWNLOAD_AUTH_PASSWORD="${DOWNLOAD_AUTH_PASSWORD}"
EOF

chmod 600 .env.init
echo "✓ Created .env.init for deploy.sh"

echo ""
echo -e "\e[32m--- Security Hardening ---\e[0m"

# Create certificate directory for HTTPS
mkdir -p ptweb-vnc/certs
chmod 700 ptweb-vnc/certs
echo "✓ Created certificate directory"

# Create logs directory
mkdir -p logs
chmod 700 logs
echo "✓ Created logs directory"

# Create authentication files for nginx
mkdir -p ptweb-vnc/pt-nginx/auth
chmod 700 ptweb-vnc/pt-nginx/auth

if [[ "$REQUIRE_DOWNLOAD_AUTH" == "true" ]]; then
    # Check if htpasswd is available
    if ! command -v htpasswd &> /dev/null; then
        echo -e "\e[33m⚠️  htpasswd not found. Skipping .htpasswd generation.\e[0m"
        echo -e "\e[33m   To enable download auth, install apache2-utils:\e[0m"
        echo -e "\e[33m   Ubuntu/Debian: sudo apt-get install apache2-utils\e[0m"
        echo -e "\e[33m   Then run: htpasswd -bc ptweb-vnc/pt-nginx/auth/.htpasswd $DOWNLOAD_AUTH_USER $DOWNLOAD_AUTH_PASSWORD\e[0m"
    else
        # Generate htpasswd file for nginx
        htpasswd -bc ptweb-vnc/pt-nginx/auth/.htpasswd "$DOWNLOAD_AUTH_USER" "$DOWNLOAD_AUTH_PASSWORD" 2>/dev/null
        chmod 600 ptweb-vnc/pt-nginx/auth/.htpasswd
        echo "✓ Generated HTTP Basic Auth credentials for /downloads"
    fi
else
    rm -f ptweb-vnc/pt-nginx/auth/.htpasswd
    echo "✓ Download authentication disabled"
fi

# Create GeoIP configuration snippet (if enabled)
if [[ "$ENABLE_GEOIP" == "true" && -n "$ALLOWED_COUNTRIES" ]]; then
    cat > ptweb-vnc/pt-nginx/conf/geoip-allowed.conf << EOF
# GeoIP Allow List - Auto-generated by secure-setup.sh
# Allowed countries: $ALLOWED_COUNTRIES

geo \$country {
    default ZZ;
EOF
    
    # Add known country IPs (this is a simplified example - use MaxMind GeoIP2 for production)
    IFS=',' read -ra COUNTRIES <<< "$ALLOWED_COUNTRIES"
    for country in "${COUNTRIES[@]}"; do
        country=$(echo "$country" | xargs)  # trim whitespace
        echo "    # $country IP ranges (placeholder - update with actual GeoIP database)" >> ptweb-vnc/pt-nginx/conf/geoip-allowed.conf
    done
    
    cat >> ptweb-vnc/pt-nginx/conf/geoip-allowed.conf << EOF
}

map \$country \$country_allowed {
    default 0;
EOF
    
    # Create allow list
    IFS=',' read -ra COUNTRIES <<< "$ALLOWED_COUNTRIES"
    for country in "${COUNTRIES[@]}"; do
        country=$(echo "$country" | xargs)  # trim whitespace
        echo "    $country 1;" >> ptweb-vnc/pt-nginx/conf/geoip-allowed.conf
    done
    
    cat >> ptweb-vnc/pt-nginx/conf/geoip-allowed.conf << EOF
}
EOF
    
    chmod 644 ptweb-vnc/pt-nginx/conf/geoip-allowed.conf
    echo "✓ Created GeoIP allowed countries config"
    echo -e "\e[33m   Note: To enable GeoIP filtering, you need MaxMind GeoIP2 database (see docs)\e[0m"
else
    rm -f ptweb-vnc/pt-nginx/conf/geoip-allowed.conf
    echo "✓ GeoIP filtering not enabled"
fi

# Update .gitignore to protect credentials
if ! grep -q ".env.secure" .gitignore 2>/dev/null; then
    cat >> .gitignore << EOF

# Security: Do NOT commit credentials!
.env.secure
.env.secure.backup
.env.init
ptweb-vnc/certs/*.pem
ptweb-vnc/certs/*.key
logs/
EOF
    echo "✓ Updated .gitignore"
else
    echo "✓ .gitignore already contains security exclusions"
fi

# Create a secure nginx config snippet for HTTPS (optional)
cat > ptweb-vnc/pt-nginx/conf/security-headers.conf << 'EOF'
# Security Headers
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-XSS-Protection "1; mode=block" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "geolocation=(), microphone=(), camera=()" always;

# Strict Transport Security (uncomment after enabling HTTPS)
# add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;

# Content Security Policy (customize as needed)
# add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline';" always;
EOF
echo "✓ Created security headers configuration"

echo ""
echo -e "\e[32m=== Setup Complete! ===\e[0m"
echo ""
echo "Next steps:"
echo ""
echo "1. Review generated files:"
echo "   - cat .env.secure"
echo ""

if [[ "$ENABLE_HTTPS" == "true" ]]; then
    echo "2. Set up HTTPS certificates:"
    echo "   Option A - Let's Encrypt:"
    echo "   sudo certbot certonly --standalone -d your-domain.com"
    echo "   sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ptweb-vnc/certs/"
    echo "   sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ptweb-vnc/certs/"
    echo ""
    echo "   Option B - Self-signed (testing only):"
    echo "   openssl req -x509 -nodes -days 365 -newkey rsa:2048 \\"
    echo "     -keyout ptweb-vnc/certs/privkey.pem \\"
    echo "     -out ptweb-vnc/certs/fullchain.pem"
    echo ""
fi

if [[ "$ENABLE_GEOIP" == "true" ]]; then
    echo "3. Set up GeoIP filtering (optional but recommended):"
    echo "   - Download MaxMind GeoIP2 City database (requires account)"
    echo "   - Place in: ptweb-vnc/pt-nginx/conf/geoip-data/"
    echo "   - Reference docs: https://nginx.org/en/docs/http/ngx_http_geoip2_module.html"
    echo ""
fi

echo "4. Deploy:"
echo "   bash deploy.sh"
echo ""
echo "5. Access at:"
if [[ "$ENABLE_HTTPS" == "true" ]]; then
    echo "   https://your-domain-or-ip/"
else
    echo "   http://your-server-ip/"
fi
echo "   Login: ptadmin / (your generated password)"
echo ""
echo "6. Verify deployment:"
echo "   bash test-deployment.sh"
echo ""
echo "📚 See SECURITY.md for complete hardening guide"
echo ""
