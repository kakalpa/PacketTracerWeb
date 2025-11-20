#!/usr/bin/env bash
set -euo pipefail

# generate-nginx-conf.sh
# Reads the project `.env` and writes both `nginx.conf` and `ptweb.conf`.
# Generates dynamic GeoIP maps based on env variables.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
ENV_FILE="$ROOT_DIR/.env"
CONF_DIR="$SCRIPT_DIR/conf"
OUT_NGINX_CONF="$SCRIPT_DIR/nginx.conf"
OUT_PTWEB_CONF="$CONF_DIR/ptweb.conf"

if [ -f "$ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ENV_FILE"
else
  echo "Warning: $ENV_FILE not found — using defaults"
  ENABLE_HTTPS=false
  NGINX_GEOIP_BLOCK=false
  GEOIP_BLOCK_COUNTRIES=""
  NGINX_GEOIP_ALLOW=false
  GEOIP_ALLOW_COUNTRIES=""
  SSL_CERT_PATH="/etc/ssl/certs/ssl-cert.pem"
  SSL_KEY_PATH="/etc/ssl/private/ssl-key.pem"
fi

# Normalize boolean values
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
NGINX_GEOIP_BLOCK=${NGINX_GEOIP_BLOCK:-false}
GEOIP_BLOCK_COUNTRIES=${GEOIP_BLOCK_COUNTRIES:-}
NGINX_GEOIP_ALLOW=${NGINX_GEOIP_ALLOW:-false}
GEOIP_ALLOW_COUNTRIES=${GEOIP_ALLOW_COUNTRIES:-}
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/ssl/certs/ssl-cert.pem}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/ssl/private/ssl-key.pem}

# Rate limiting defaults
NGINX_RATE_LIMIT_ENABLE=${NGINX_RATE_LIMIT_ENABLE:-false}
NGINX_RATE_LIMIT_RATE=${NGINX_RATE_LIMIT_RATE:-10r/s}   # e.g. "10r/s" or "100r/m"
NGINX_RATE_LIMIT_BURST=${NGINX_RATE_LIMIT_BURST:-20}
NGINX_RATE_LIMIT_ZONE_SIZE=${NGINX_RATE_LIMIT_ZONE_SIZE:-10m} # shared memory zone size

mkdir -p "$CONF_DIR"

# Note: ALLOW mode takes precedence over BLOCK mode in the generated config.
# Both can be enabled simultaneously, but ALLOW checks are evaluated first.
# If a trusted IP is bypassed or a request matches ALLOW countries, BLOCK is not checked.
# This ensures ALLOW whitelist is always honored when enabled.


# ============================================================================
# Detect public IP for trusted IPs bypass (if PRODUCTION_MODE enabled)
# ============================================================================
PRODUCTION_MODE=${PRODUCTION_MODE:-false}
PUBLIC_IP=${PUBLIC_IP:-}
TRUSTED_IPS_REGEX="(127\\.|10\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.|192\\.168\\.)"

if [ "$PRODUCTION_MODE" = "true" ] || [ "$PRODUCTION_MODE" = "1" ] || [ -n "$PUBLIC_IP" ]; then
  echo "ℹ️  Trusted IPs mode enabled (PRODUCTION_MODE=$PRODUCTION_MODE, PUBLIC_IP=${PUBLIC_IP:-auto})" >&2
  
  # Detect public IP if not provided
  if [ -z "$PUBLIC_IP" ]; then
    echo "  Detecting public IP via ifconfig.co..." >&2
    PUBLIC_IP=$(curl -s --max-time 5 https://ifconfig.co 2>/dev/null || echo "")
    if [ -n "$PUBLIC_IP" ]; then
      echo "  ✓ Detected public IP: $PUBLIC_IP" >&2
    else
      echo "  ⚠ Could not detect public IP (network unavailable)" >&2
    fi
  fi
  
  # Add public IP to trusted IPs regex if detected
  if [ -n "$PUBLIC_IP" ]; then
    ESCAPED_IP=$(echo "$PUBLIC_IP" | sed 's/\\./\\\./g')
    TRUSTED_IPS_REGEX="$TRUSTED_IPS_REGEX|$ESCAPED_IP"
    echo "  ✓ Added public IP $PUBLIC_IP to trusted IPs bypass list" >&2
  fi
else
  echo "ℹ️  Development mode (PRODUCTION_MODE=false). Local IPs only in bypass list." >&2
fi

echo "Generating nginx configs (NGINX_GEOIP_ALLOW=$NGINX_GEOIP_ALLOW, GEOIP_ALLOW_COUNTRIES=$GEOIP_ALLOW_COUNTRIES)"

# Backup existing configs if present
if [ -f "$OUT_NGINX_CONF" ]; then
  cp -a "$OUT_NGINX_CONF" "$OUT_NGINX_CONF.bak.$(date +%s)" || true
fi
if [ -f "$OUT_PTWEB_CONF" ]; then
  cp -a "$OUT_PTWEB_CONF" "$OUT_PTWEB_CONF.bak.$(date +%s)" || true
fi

# ============================================================================
# PART 1: Generate nginx.conf with dynamic GeoIP maps
# ============================================================================
{
  cat << 'NGINX_HEADER_EOF'

user nginx;
worker_processes auto;

error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript application/json application/javascript application/xml+rss application/rss+xml font/truetype font/opentype application/vnd.ms-fontobject image/svg+xml;

    # Docker DNS resolver
    resolver 127.0.0.11:53 valid=10s;
    resolver_timeout 5s;

NGINX_HEADER_EOF

  # Add GeoIP support if enabled
  if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ]; then
    cat << 'GEOIP_COMMON_EOF'
    # GeoIP support - http-level configuration
    geoip_country /usr/share/GeoIP/GeoIP.dat;
    geoip_proxy_recursive on;

GEOIP_COMMON_EOF

    # Generate ALLOW mode map if enabled
    if [ "$NGINX_GEOIP_ALLOW" = "true" ] && [ -n "$GEOIP_ALLOW_COUNTRIES" ]; then
      cat << 'EOF'
    # ALLOW mode (whitelist): Only permit traffic from specified countries
    # Returns 1 if country is in allow list, 0 (deny) for all others including unknown
EOF
      echo "    map \$geoip_country_code \$allowed_country {"
      echo "        default 0;  # Default to 0 (deny all unless explicitly allowed)"
      
      # Add each allowed country
      IFS=',' read -ra COUNTRIES <<< "$GEOIP_ALLOW_COUNTRIES"
      for country in "${COUNTRIES[@]}"; do
        country=$(echo "$country" | xargs)  # trim whitespace
        echo "        $country 1;"
      done
      echo "    }"
      echo ""
    else
      cat << 'EOF'
    # ALLOW mode disabled - all countries allowed
    map $geoip_country_code $allowed_country {
        default 1;  # Default to 1 (allow all)
    }
EOF
    fi

    # Generate BLOCK mode map if enabled
    if [ "$NGINX_GEOIP_BLOCK" = "true" ] && [ -n "$GEOIP_BLOCK_COUNTRIES" ]; then
      cat << 'EOF'
    # BLOCK mode (blacklist): Deny traffic from specified countries
    # Returns 1 if country is in block list, 0 (allow) for all others
EOF
      echo "    map \$geoip_country_code \$blocked_country {"
      echo "        default 0;  # Default to 0 (allow unless explicitly blocked)"
      
      # Add each blocked country
      IFS=',' read -ra COUNTRIES <<< "$GEOIP_BLOCK_COUNTRIES"
      for country in "${COUNTRIES[@]}"; do
        country=$(echo "$country" | xargs)  # trim whitespace
        echo "        $country 1;"
      done
      echo "    }"
      echo ""
    else
      cat << 'EOF'
    # BLOCK mode disabled - no countries blocked
    map $geoip_country_code $blocked_country {
        default 0;  # Default to 0 (don't block)
    }
EOF
    fi
  fi

  # Include all server configurations from conf.d
  cat << 'NGINX_FOOTER_EOF'
    # Include all server configurations from conf.d
    include /etc/nginx/conf.d/*.conf;
}
NGINX_FOOTER_EOF
} > "$OUT_NGINX_CONF"

echo "✓ Generated $OUT_NGINX_CONF with dynamic GeoIP maps"

# ============================================================================
# PART 2: Generate ptweb.conf (location blocks only - maps are in nginx.conf)
# ============================================================================

render_geoip_check() {
  # Generates the GeoIP filtering check that should be placed at the start of location blocks
  # Bypasses checks for trusted/local/private IPs (including public IP if PRODUCTION_MODE enabled)
  # Both ALLOW and BLOCK can be enabled; ALLOW takes precedence.
  
  local has_geoip_check=false
  
  echo "    # Bypass GeoIP for trusted IPs (local/private/public)"
  echo "    if (\$remote_addr ~ ^$TRUSTED_IPS_REGEX) {"
  echo "      set \$allowed_country 1;"
  echo "      set \$blocked_country 0;"
  echo "    }"
  
  if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_ALLOW" = "1" ]; then
    if [ -n "$GEOIP_ALLOW_COUNTRIES" ]; then
      echo "    # ALLOW mode: only permitted countries allowed"
      echo "    if (\$allowed_country = 0) { return 444; }"
      has_geoip_check=true
    fi
  fi
  
  if [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; then
    if [ -n "$GEOIP_BLOCK_COUNTRIES" ]; then
      echo "    # BLOCK mode: blocked countries denied"
      echo "    if (\$blocked_country = 1) { return 444; }"
      has_geoip_check=true
    fi
  fi
}

render_rate_limit_directive() {
  if [ "$NGINX_RATE_LIMIT_ENABLE" = "true" ] || [ "$NGINX_RATE_LIMIT_ENABLE" = "1" ]; then
    echo "    limit_req zone=pt_req_zone burst=${NGINX_RATE_LIMIT_BURST} nodelay;"
  fi
}

render_common_server_block() {
  # Output location blocks with GeoIP checks embedded
  cat <<'EOF'
  charset utf-8;

  # Serve shared downloads with highest priority
  location ^~ /downloads/ {
EOF
  render_geoip_check
  cat <<'EOF'
    alias /shared/;
    autoindex on;
    autoindex_exact_size off;
    autoindex_localtime on;
  }

  # File manager interface
  location ^~ /files {
EOF
  render_geoip_check
  cat <<'EOF'
    rewrite ^/files/?$ /file-manager.html break;
  }

  # Root location - proxy Guacamole at /
  location / {
EOF
  render_geoip_check
  cat <<'EOF'
    proxy_redirect off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;

    # WebSocket support for Guacamole tunneling
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    client_max_body_size 10m;
EOF
  render_rate_limit_directive
  cat <<'EOF'
    client_body_buffer_size 128k;
    proxy_connect_timeout 90;
    proxy_send_timeout 90;
    proxy_read_timeout 90;
    proxy_buffers 32 4k;
    proxy_pass http://pt-guacamole:8080/guacamole/;
  }

  location ~ \.ht {
    deny all;
  }
EOF
}

# ============================================================================
# Write ptweb.conf file
# ============================================================================

{
  cat <<'EOF'
# This file is GENERATED by generate-nginx-conf.sh
# Do not edit manually — changes will be overwritten on next deploy

EOF

  # Add rate limit zone definition at top level (http context level, but in this file)
  if [ "$NGINX_RATE_LIMIT_ENABLE" = "true" ] || [ "$NGINX_RATE_LIMIT_ENABLE" = "1" ]; then
    cat <<EOF
# Rate limiting zone
limit_req_zone \$binary_remote_addr zone=pt_req_zone:${NGINX_RATE_LIMIT_ZONE_SIZE} rate=${NGINX_RATE_LIMIT_RATE};

EOF
  fi

  # HTTPS configuration
  if [ "$ENABLE_HTTPS" = "true" ] || [ "$ENABLE_HTTPS" = "1" ]; then
    cat <<EOF
# HTTP -> HTTPS redirect
server {
  listen 80;
  server_name localhost;
  return 301 https://\$host\$request_uri;
}

# Main HTTPS server
server {
    listen 443 ssl;
    http2 on;
    server_name localhost;

    ssl_certificate ${SSL_CERT_PATH};
    ssl_certificate_key ${SSL_KEY_PATH};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

EOF
  else
    # Plain HTTP server
    cat <<'EOF'
# Main HTTP server
server {
    listen 80;
    server_name localhost;

EOF
  fi

  # Common server block (location directives with GeoIP checks)
  render_common_server_block

  cat <<'EOF'

    error_page   500 502 503 504  /50x.html;
    location = /50x.html {
        root   /usr/share/nginx/html;
    }
}
EOF

} > "$OUT_PTWEB_CONF"

echo "✓ Wrote $OUT_NGINX_CONF (http-level configuration with GeoIP maps)"
echo "✓ Wrote $OUT_PTWEB_CONF (server/location blocks with GeoIP checks)"

exit 0
