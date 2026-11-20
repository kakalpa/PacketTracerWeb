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

load_env_file() {
  local env_file="$1"
  local line key val
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line%$'\r'}"
    [[ -z "${line//[[:space:]]/}" || "$line" =~ ^[[:space:]]*# ]] && continue
    [[ "$line" =~ ^[[:space:]]*export[[:space:]]+(.*)$ ]] && line="${BASH_REMATCH[1]}"
    [[ "$line" != *=* ]] && continue
    key="${line%%=*}"
    val="${line#*=}"
    key="${key//[[:space:]]/}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    if [[ "$val" =~ ^\"(.*)\"$ ]]; then
      val="${BASH_REMATCH[1]}"
    elif [[ "$val" =~ ^\'(.*)\'$ ]]; then
      val="${BASH_REMATCH[1]}"
    fi
    case "$key" in
      PRODUCTION_MODE|PUBLIC_IP|ENABLE_HTTPS|TLS_MODE|SERVER_NAME|\
      SSL_CERT_PATH|SSL_KEY_PATH|\
      CERTBOT_ENABLED|CERTBOT_DOMAIN|CERTBOT_EXTRA_DOMAINS|CERTBOT_EMAIL|\
      CERTBOT_CHALLENGE_TYPE|CERTBOT_STAGING|CERTBOT_AUTO_RENEW|CERTBOT_WEBROOT|\
      NGINX_GEOIP_BLOCK|GEOIP_BLOCK_COUNTRIES|NGINX_GEOIP_ALLOW|GEOIP_ALLOW_COUNTRIES|\
      NGINX_RATE_LIMIT_ENABLE|NGINX_RATE_LIMIT_RATE|NGINX_RATE_LIMIT_BURST|NGINX_RATE_LIMIT_ZONE_SIZE)
        printf -v "$key" '%s' "$val"
        ;;
    esac
  done < "$env_file"
}

if [ -f "$ENV_FILE" ]; then
  load_env_file "$ENV_FILE"
else
  echo "Warning: $ENV_FILE not found — using defaults"
  ENABLE_HTTPS=false
  NGINX_GEOIP_BLOCK=false
  GEOIP_BLOCK_COUNTRIES=""
  NGINX_GEOIP_ALLOW=false
  GEOIP_ALLOW_COUNTRIES=""
  SSL_CERT_PATH="/etc/ssl/ptweb/server.crt"
  SSL_KEY_PATH="/etc/ssl/ptweb/server.key"
fi

# Normalize boolean & TLS/Certbot values
ENABLE_HTTPS=${ENABLE_HTTPS:-false}
TLS_MODE=${TLS_MODE:-self-signed}
SERVER_NAME=${SERVER_NAME:-}
CERTBOT_ENABLED=${CERTBOT_ENABLED:-false}
CERTBOT_DOMAIN=${CERTBOT_DOMAIN:-}
CERTBOT_EXTRA_DOMAINS=${CERTBOT_EXTRA_DOMAINS:-}
CERTBOT_EMAIL=${CERTBOT_EMAIL:-}
CERTBOT_CHALLENGE_TYPE=${CERTBOT_CHALLENGE_TYPE:-http-01}
CERTBOT_STAGING=${CERTBOT_STAGING:-false}
CERTBOT_AUTO_RENEW=${CERTBOT_AUTO_RENEW:-true}
CERTBOT_WEBROOT=${CERTBOT_WEBROOT:-/var/www/certbot}
NGINX_GEOIP_BLOCK=${NGINX_GEOIP_BLOCK:-false}
GEOIP_BLOCK_COUNTRIES=${GEOIP_BLOCK_COUNTRIES:-}
NGINX_GEOIP_ALLOW=${NGINX_GEOIP_ALLOW:-false}
GEOIP_ALLOW_COUNTRIES=${GEOIP_ALLOW_COUNTRIES:-}
SSL_CERT_PATH=${SSL_CERT_PATH:-/etc/ssl/ptweb/server.crt}
SSL_KEY_PATH=${SSL_KEY_PATH:-/etc/ssl/ptweb/server.key}

# Normalize legacy single-file SSL paths to /etc/ssl/ptweb directory mount
case "$SSL_CERT_PATH" in
  ""|"/etc/ssl/certs/server.crt"|"/etc/ssl/certs/ssl-cert.pem")
    SSL_CERT_PATH="/etc/ssl/ptweb/server.crt"
    ;;
esac
case "$SSL_KEY_PATH" in
  ""|"/etc/ssl/private/server.key"|"/etc/ssl/private/ssl-key.pem")
    SSL_KEY_PATH="/etc/ssl/ptweb/server.key"
    ;;
esac

# Validate CERTBOT_WEBROOT
if [[ ! "$CERTBOT_WEBROOT" =~ ^/[A-Za-z0-9._/-]+$ ]] || [[ "$CERTBOT_WEBROOT" == *..* ]] || [[ "$CERTBOT_WEBROOT" == *//* ]] || [[ "$CERTBOT_WEBROOT" == "/." ]] || [[ "$CERTBOT_WEBROOT" == */./* ]] || [[ "$CERTBOT_WEBROOT" == */. ]]; then
  echo "ERROR: Invalid CERTBOT_WEBROOT: '$CERTBOT_WEBROOT'" >&2
  exit 1
fi

# Resolve and validate EFFECTIVE_SERVER_NAME (wildcard-safe)
RAW_SERVER_NAME=""
if [ -n "${SERVER_NAME//[[:space:]]/}" ]; then
  RAW_SERVER_NAME="${SERVER_NAME//,/ }"
elif [ -n "${CERTBOT_DOMAIN//[[:space:]]/}" ]; then
  RAW_SERVER_NAME="$CERTBOT_DOMAIN ${CERTBOT_EXTRA_DOMAINS//,/ }"
else
  RAW_SERVER_NAME="localhost"
fi

set -f
IFS=' ' read -ra SERVER_TOKENS <<< "$RAW_SERVER_NAME"
set +f

VALIDATED_TOKENS=()
LABEL_RE='[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?'
FQDN_RE="^(${LABEL_RE}\.)+${LABEL_RE}$"
WILDCARD_RE="^\*\.${LABEL_RE}(\.${LABEL_RE})+$"

for tok in "${SERVER_TOKENS[@]}"; do
  [ -z "$tok" ] && continue
  if [[ ! "$tok" =~ ^[A-Za-z0-9._*-]+$ ]] || [[ "$tok" == -* ]] || [[ "$tok" == *..* ]]; then
    echo "ERROR: Invalid server_name token: '$tok'" >&2
    exit 1
  fi
  if [[ "$tok" == "localhost" ]] || [[ "$tok" =~ $FQDN_RE ]] || [[ "$tok" =~ $WILDCARD_RE ]]; then
    VALIDATED_TOKENS+=("$tok")
  else
    echo "ERROR: Invalid server_name hostname token: '$tok'" >&2
    exit 1
  fi
done

if [ ${#VALIDATED_TOKENS[@]} -eq 0 ]; then
  EFFECTIVE_SERVER_NAME="localhost"
else
  EFFECTIVE_SERVER_NAME="${VALIDATED_TOKENS[*]}"
fi

# Resolve EFFECTIVE_CERT_PATH / EFFECTIVE_KEY_PATH with bootstrap fallback
EFFECTIVE_CERT_PATH="$SSL_CERT_PATH"
EFFECTIVE_KEY_PATH="$SSL_KEY_PATH"
USING_CERTBOT_CERT=false

if [ "$TLS_MODE" = "certbot" ]; then
  if [ -n "$CERTBOT_DOMAIN" ]; then
    if [[ ! "$CERTBOT_DOMAIN" =~ $FQDN_RE ]] || [[ "$CERTBOT_DOMAIN" == *..* ]] || [ ${#CERTBOT_DOMAIN} -gt 253 ]; then
      echo "ERROR: Invalid CERTBOT_DOMAIN: '$CERTBOT_DOMAIN'" >&2
      exit 1
    fi
    LE_HOST_CERT="$ROOT_DIR/certbot/conf/live/${CERTBOT_DOMAIN}/fullchain.pem"
    LE_HOST_KEY="$ROOT_DIR/certbot/conf/live/${CERTBOT_DOMAIN}/privkey.pem"
    if [ -s "$LE_HOST_CERT" ] && [ -s "$LE_HOST_KEY" ]; then
      EFFECTIVE_CERT_PATH="/etc/letsencrypt/live/${CERTBOT_DOMAIN}/fullchain.pem"
      EFFECTIVE_KEY_PATH="/etc/letsencrypt/live/${CERTBOT_DOMAIN}/privkey.pem"
      USING_CERTBOT_CERT=true
    else
      echo "ℹ️  TLS_MODE=certbot but LE cert not present at $LE_HOST_CERT — falling back to /etc/ssl/ptweb/server.{crt,key}" >&2
      EFFECTIVE_CERT_PATH="/etc/ssl/ptweb/server.crt"
      EFFECTIVE_KEY_PATH="/etc/ssl/ptweb/server.key"
    fi
  else
    if [[ "$EFFECTIVE_CERT_PATH" == /etc/letsencrypt/* ]] || [[ "$EFFECTIVE_KEY_PATH" == /etc/letsencrypt/* ]]; then
      LE_REL_CERT="${EFFECTIVE_CERT_PATH#/etc/letsencrypt/}"
      LE_REL_KEY="${EFFECTIVE_KEY_PATH#/etc/letsencrypt/}"
      if [ -s "$ROOT_DIR/certbot/conf/$LE_REL_CERT" ] && [ -s "$ROOT_DIR/certbot/conf/$LE_REL_KEY" ]; then
        USING_CERTBOT_CERT=true
      else
        echo "ℹ️  TLS_MODE=certbot with empty CERTBOT_DOMAIN and missing LE cert — falling back to /etc/ssl/ptweb/server.{crt,key}" >&2
        EFFECTIVE_CERT_PATH="/etc/ssl/ptweb/server.crt"
        EFFECTIVE_KEY_PATH="/etc/ssl/ptweb/server.key"
      fi
    fi
  fi
elif [[ "$EFFECTIVE_CERT_PATH" == /etc/letsencrypt/* ]] || [[ "$EFFECTIVE_KEY_PATH" == /etc/letsencrypt/* ]]; then
  LE_REL_CERT="${EFFECTIVE_CERT_PATH#/etc/letsencrypt/}"
  LE_REL_KEY="${EFFECTIVE_KEY_PATH#/etc/letsencrypt/}"
  if [ ! -s "$ROOT_DIR/certbot/conf/$LE_REL_CERT" ] || [ ! -s "$ROOT_DIR/certbot/conf/$LE_REL_KEY" ]; then
    echo "ℹ️  Missing LE cert at $EFFECTIVE_CERT_PATH — falling back to /etc/ssl/ptweb/server.{crt,key}" >&2
    EFFECTIVE_CERT_PATH="/etc/ssl/ptweb/server.crt"
    EFFECTIVE_KEY_PATH="/etc/ssl/ptweb/server.key"
  fi
fi

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
is_valid_ip() {
  local ip="$1"
  if [[ "$ip" =~ ^([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})\.([0-9]{1,3})$ ]]; then
    local o1="${BASH_REMATCH[1]}" o2="${BASH_REMATCH[2]}" o3="${BASH_REMATCH[3]}" o4="${BASH_REMATCH[4]}"
    [ "$o1" -le 255 ] && [ "$o2" -le 255 ] && [ "$o3" -le 255 ] && [ "$o4" -le 255 ] 2>/dev/null
    return $?
  fi
  if [[ "$ip" == *:* ]] && [[ "$ip" =~ ^[0-9A-Fa-f:]+$ ]] && [[ "$ip" != *:::* ]]; then
    return 0
  fi
  return 1
}

PRODUCTION_MODE=${PRODUCTION_MODE:-false}
PUBLIC_IP=${PUBLIC_IP:-}
TRUSTED_IPS_REGEX="(127\\.|10\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.|192\\.168\\.)"

if [ "$PRODUCTION_MODE" = "true" ] || [ "$PRODUCTION_MODE" = "1" ] || [ -n "$PUBLIC_IP" ]; then
  echo "ℹ️  Trusted IPs mode enabled (PRODUCTION_MODE=$PRODUCTION_MODE, PUBLIC_IP=${PUBLIC_IP:-auto})" >&2

  # Detect public IP if not provided
  if [ -z "$PUBLIC_IP" ]; then
    echo "  Detecting public IP via ifconfig.co..." >&2
    PUBLIC_IP=$(curl -s --max-time 5 https://ifconfig.co 2>/dev/null | tr -d '\r\n' | xargs || true)
    if [ -n "$PUBLIC_IP" ] && is_valid_ip "$PUBLIC_IP"; then
      echo "  ✓ Detected public IP: $PUBLIC_IP" >&2
    elif [ -n "$PUBLIC_IP" ]; then
      echo "  ⚠ Ignoring invalid detected public IP: '$PUBLIC_IP'" >&2
      PUBLIC_IP=""
    else
      echo "  ⚠ Could not detect public IP (network unavailable)" >&2
    fi
  else
    PUBLIC_IP=$(printf '%s' "$PUBLIC_IP" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if ! is_valid_ip "$PUBLIC_IP"; then
      echo "  ⚠ Ignoring invalid PUBLIC_IP from .env: '$PUBLIC_IP'" >&2
      PUBLIC_IP=""
    fi
  fi

  # Add validated public IP (anchored with $) to trusted IPs regex
  if [ -n "$PUBLIC_IP" ]; then
    ESCAPED_IP=$(printf '%s' "$PUBLIC_IP" | sed 's/[.[\*^$()+?{|\\]/\\&/g')
    TRUSTED_IPS_REGEX="(127\\.|10\\.|172\\.(1[6-9]|2[0-9]|3[01])\\.|192\\.168\\.|${ESCAPED_IP}\$)"
    echo "  ✓ Added public IP $PUBLIC_IP to trusted IPs bypass list" >&2
  fi
else
  echo "ℹ️  Development mode (PRODUCTION_MODE=false). Local IPs only in bypass list." >&2
fi

parse_country_list() {
  local raw="$1"
  local -n _out="$2"
  _out=()
  local item
  set -f
  IFS=',' read -ra _items <<< "$raw"
  set +f
  for item in "${_items[@]}"; do
    item="${item#"${item%%[![:space:]]*}"}"
    item="${item%"${item##*[![:space:]]}"}"
    [ -z "$item" ] && continue
    item="${item^^}"
    if [[ ! "$item" =~ ^[A-Z0-9]{2}$ ]]; then
      echo "ERROR: Invalid GeoIP country code: '$item'" >&2
      exit 1
    fi
    _out+=("$item")
  done
}

ALLOW_COUNTRIES_LIST=()
BLOCK_COUNTRIES_LIST=()
if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_ALLOW" = "1" ]; then
  parse_country_list "$GEOIP_ALLOW_COUNTRIES" ALLOW_COUNTRIES_LIST
fi
if [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; then
  parse_country_list "$GEOIP_BLOCK_COUNTRIES" BLOCK_COUNTRIES_LIST
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
    server_names_hash_bucket_size 128;

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
  if [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_ALLOW" = "1" ] || [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; then
    cat << 'GEOIP_COMMON_EOF'
    # GeoIP support - http-level configuration
    geoip_country /usr/share/GeoIP/GeoIP.dat;
    geoip_proxy_recursive on;

GEOIP_COMMON_EOF

    # Generate ALLOW mode map if enabled
    if { [ "$NGINX_GEOIP_ALLOW" = "true" ] || [ "$NGINX_GEOIP_ALLOW" = "1" ]; } && [ ${#ALLOW_COUNTRIES_LIST[@]} -gt 0 ]; then
      cat << 'EOF'
    # ALLOW mode (whitelist): Only permit traffic from specified countries
    # Returns 1 if country is in allow list, 0 (deny) for all others including unknown
EOF
      echo "    map \$geoip_country_code \$allowed_country {"
      echo "        default 0;  # Default to 0 (deny all unless explicitly allowed)"
      
      # Add each allowed country
      for country in "${ALLOW_COUNTRIES_LIST[@]}"; do
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
    if { [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; } && [ ${#BLOCK_COUNTRIES_LIST[@]} -gt 0 ]; then
      cat << 'EOF'
    # BLOCK mode (blacklist): Deny traffic from specified countries
    # Returns 1 if country is in block list, 0 (allow) for all others
EOF
      echo "    map \$geoip_country_code \$blocked_country {"
      echo "        default 0;  # Default to 0 (allow unless explicitly blocked)"
      
      # Add each blocked country
      for country in "${BLOCK_COUNTRIES_LIST[@]}"; do
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
    # WebSocket connection upgrade mapping for Guacamole
    map $http_upgrade $connection_upgrade {
        default upgrade;
        '' close;
    }

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
    if [ ${#ALLOW_COUNTRIES_LIST[@]} -gt 0 ]; then
      echo "    # ALLOW mode: only permitted countries allowed"
      echo "    if (\$allowed_country = 0) { return 444; }"
      has_geoip_check=true
    fi
  fi
  
  if [ "$NGINX_GEOIP_BLOCK" = "true" ] || [ "$NGINX_GEOIP_BLOCK" = "1" ]; then
    if [ ${#BLOCK_COUNTRIES_LIST[@]} -gt 0 ]; then
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

  # Protected internal storage serving - accessible ONLY via X-Accel-Redirect
  location ^~ /internal/downloads/ {
    internal;
    alias /shared/instances/;
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    gzip off;
    default_type application/octet-stream;
    add_header X-Content-Type-Options nosniff always;
    add_header Content-Security-Policy "default-src 'none'" always;
  }

  # Protected internal course materials - accessible ONLY via X-Accel-Redirect
  location ^~ /internal/common/ {
    internal;
    alias /shared/common/;
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    gzip off;
    default_type application/octet-stream;
    add_header X-Content-Type-Options nosniff always;
    add_header Content-Security-Policy "default-src 'none'" always;
  }

  # Reverse proxy for Student File Download API
  location ^~ /api/student/files/ {
EOF
  render_geoip_check
  render_rate_limit_directive
  cat <<'EOF'
    set $pt_mgmt_upstream http://pt-management:5000;
    proxy_pass $pt_mgmt_upstream;
    proxy_redirect off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  # File manager interface
  location ^~ /files {
EOF
  render_geoip_check
  cat <<'EOF'
    rewrite ^/files/?$ /file-manager.html break;
  }

  # Student Downloads Portal
  location ^~ /my-files {
EOF
  render_geoip_check
  render_rate_limit_directive
  cat <<'EOF'
    set $pt_mgmt_upstream http://pt-management:5000;
    proxy_pass $pt_mgmt_upstream;
    proxy_redirect off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
  }

  # Downloads endpoint - redirects browser clients to /my-files while blocking unauthenticated raw listings
  location ^~ /downloads {
EOF
  render_geoip_check
  render_rate_limit_directive
  cat <<'EOF'
    set $pt_mgmt_upstream http://pt-management:5000;
    proxy_pass $pt_mgmt_upstream;
    proxy_redirect off;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
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
    proxy_buffering off;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_cookie_path /guacamole/ /;

    client_max_body_size 10m;
EOF
  render_rate_limit_directive
  cat <<'EOF'
    client_body_buffer_size 128k;
    proxy_connect_timeout 90;
    proxy_send_timeout 90;
    proxy_read_timeout 90;
    proxy_pass http://pt-guacamole:8080/guacamole/;
  }

  location ~ /\.ht {
    deny all;
  }
EOF
}

render_acme_location() {
  cat <<EOF
    location ^~ /.well-known/acme-challenge/ {
        root ${CERTBOT_WEBROOT};
        default_type "text/plain";
        try_files \$uri =404;
    }

EOF
}

render_ssl_directives() {
  cat <<EOF
    ssl_certificate ${EFFECTIVE_CERT_PATH};
    ssl_certificate_key ${EFFECTIVE_KEY_PATH};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;
    ssl_session_tickets off;
EOF
  if [ "$TLS_MODE" = "certbot" ] && [ "$USING_CERTBOT_CERT" = "true" ]; then
    echo '    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;'
  fi
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
# HTTP -> HTTPS redirect with ACME HTTP-01 carve-out
server {
  listen 80;
  server_name ${EFFECTIVE_SERVER_NAME};

  location ^~ /.well-known/acme-challenge/ {
    root ${CERTBOT_WEBROOT};
    default_type "text/plain";
    try_files \$uri =404;
  }

  location / {
    return 301 https://\$host\$request_uri;
  }
}

# Main HTTPS server
server {
    listen 443 ssl;
    http2 on;
    server_name ${EFFECTIVE_SERVER_NAME};

EOF
    render_ssl_directives
    echo ""
    render_acme_location
  else
    # Plain HTTP server
    cat <<EOF
# Main HTTP server
server {
    listen 80;
    server_name ${EFFECTIVE_SERVER_NAME};

EOF
    render_acme_location
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

  # ============================================================================
  # Management Interface Server on Port 5000 (with auto HTTP -> HTTPS redirect)
  # ============================================================================
  if [ "$ENABLE_HTTPS" = "true" ] || [ "$ENABLE_HTTPS" = "1" ]; then
    cat <<EOF

# Management Interface HTTPS server with auto-redirection on port 5000
server {
    listen 5000 ssl;
    http2 on;
    server_name ${EFFECTIVE_SERVER_NAME};

EOF
    render_ssl_directives
    cat <<EOF

    # Auto-redirect plain HTTP to HTTPS on port 5000
    error_page 497 =301 https://\$host:5000\$request_uri;

    location / {
        set \$pt_mgmt_upstream http://pt-management:5000;
        proxy_pass \$pt_mgmt_upstream;
        proxy_redirect off;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        client_max_body_size 500m;
        client_body_buffer_size 128k;
        proxy_connect_timeout 90;
        proxy_send_timeout 150;
        proxy_read_timeout 150;
        proxy_buffers 32 4k;
    }
}
EOF
  else
    cat <<EOF

# Management Interface HTTP server on port 5000
server {
    listen 5000;
    server_name ${EFFECTIVE_SERVER_NAME};

    location / {
        set \$pt_mgmt_upstream http://pt-management:5000;
        proxy_pass \$pt_mgmt_upstream;
        proxy_redirect off;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto http;

        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";

        client_max_body_size 500m;
        client_body_buffer_size 128k;
        proxy_connect_timeout 90;
        proxy_send_timeout 150;
        proxy_read_timeout 150;
        proxy_buffers 32 4k;
    }
}
EOF
  fi

} > "$OUT_PTWEB_CONF"

echo "✓ Wrote $OUT_NGINX_CONF (http-level configuration with GeoIP maps)"
echo "✓ Wrote $OUT_PTWEB_CONF (server/location blocks with GeoIP checks)"

exit 0
