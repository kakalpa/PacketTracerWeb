````markdown
# Nginx config generation for PacketTracerWeb

This directory contains a helper script to generate an nginx config (`ptweb.conf`) from the project-level `.env` file with support for HTTPS and GeoIP filtering (both blocklist and allowlist modes).

## Usage

1. Edit the project `.env` at the repository root to configure:
   - `ENABLE_HTTPS=true|false` — Enable HTTPS with redirect
   - `NGINX_GEOIP_BLOCK=true|false` — Enable GeoIP blocklist (blacklist) mode
   - `GEOIP_BLOCK_COUNTRIES` — Comma-separated country codes to block (e.g., `CN,RU,IR`)
   - `NGINX_GEOIP_ALLOW=true|false` — Enable GeoIP allowlist (whitelist) mode
   - `GEOIP_ALLOW_COUNTRIES` — Comma-separated country codes to allow (e.g., `US,CA,GB,AU`)
   - `SSL_CERT_PATH` and `SSL_KEY_PATH` — Paths inside container to cert/key files

2. Make the generator executable and run it:

```bash
chmod +x generate-nginx-conf.sh
./generate-nginx-conf.sh
```

This writes `conf/ptweb.conf` (backing up any existing file). The `docker-compose.yml` mounts `pt-nginx/conf` into the nginx container, so after generating the config you can start the stack as before (for example `docker-compose up -d`).

## GeoIP Filtering Modes

### ALLOW Mode (Whitelist)
When `NGINX_GEOIP_ALLOW=true`, only traffic from countries in `GEOIP_ALLOW_COUNTRIES` is permitted. All other traffic is rejected with a 444 response (connection close).

**Example in `.env`:**
```properties
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU
```

### BLOCK Mode (Blacklist)
When `NGINX_GEOIP_BLOCK=true`, traffic from countries in `GEOIP_BLOCK_COUNTRIES` is rejected. All other traffic is allowed.

**Example in `.env`:**
```properties
NGINX_GEOIP_BLOCK=true
GEOIP_BLOCK_COUNTRIES=CN,RU,IR
```

### Priority
If both `NGINX_GEOIP_ALLOW` and `NGINX_GEOIP_BLOCK` are enabled, **ALLOW mode takes precedence** (acts as the primary filter). If `GEOIP_ALLOW_COUNTRIES` is empty but `NGINX_GEOIP_ALLOW=true`, no allowlist filtering is applied.

## Example Configurations

### No GeoIP Filtering (HTTP only)
```properties
ENABLE_HTTPS=false
NGINX_GEOIP_ALLOW=false
NGINX_GEOIP_BLOCK=false
```

### HTTPS with Blocklist
```properties
ENABLE_HTTPS=true
NGINX_GEOIP_BLOCK=true
GEOIP_BLOCK_COUNTRIES=CN,RU,IR
SSL_CERT_PATH=/etc/ssl/certs/ssl-cert.pem
SSL_KEY_PATH=/etc/ssl/private/ssl-key.pem
```

### HTTPS with Allowlist
```properties
ENABLE_HTTPS=true
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,NZ
SSL_CERT_PATH=/etc/ssl/certs/ssl-cert.pem
SSL_KEY_PATH=/etc/ssl/private/ssl-key.pem
```

## Important Requirements

### GeoIP Database
For GeoIP filtering to work, the GeoIP database must be available inside the nginx container:

**Option 1: Install via apt** (recommended)
```bash
docker exec pt-nginx1 apt-get update
docker exec pt-nginx1 apt-get install -y geoip-database
```

**Option 2: Mount the database file**
Add to your Docker run command or compose file:
```bash
-v /usr/share/GeoIP/GeoIP.dat:/usr/share/GeoIP/GeoIP.dat:ro
```

### HTTPS Certificates
If `ENABLE_HTTPS=true`, ensure certificates are available at the paths specified by `SSL_CERT_PATH` and `SSL_KEY_PATH`:

**Option 1: Mount your certificates**
```bash
docker run ... \
  -v /path/to/cert.pem:/etc/ssl/certs/ssl-cert.pem:ro \
  -v /path/to/key.pem:/etc/ssl/private/ssl-key.pem:ro \
  ...
```

**Option 2: Update paths in `.env`**
If your certs are at different locations, update the paths accordingly.

## Notes & Caveats

- The generator adds GeoIP mappings at the nginx `http` context level and filtering checks in each server block
- 444 is a special nginx response code that closes the connection without sending a response to the client
- The generator does not create certificates or download GeoIP databases; these must be provided separately
- This is a lightweight helper; production deployments should use proper templating or configuration management and ensure the nginx GeoIP module is available
- If `ENABLE_HTTPS`, `NGINX_GEOIP_ALLOW`, and `NGINX_GEOIP_BLOCK` are all disabled or country lists are empty, the generated config will be plain HTTP with no filtering

## Troubleshooting

**GeoIP database not found:**
```
If you see errors like "geoip_country: open() /usr/share/GeoIP/GeoIP.dat failed",
install the database inside the nginx container or mount it as shown above.
```

**Certificates not found:**
```
If you see SSL errors, verify that SSL_CERT_PATH and SSL_KEY_PATH point to files
that are mounted inside the nginx container.
```

**Regenerate config:**
```bash
./generate-nginx-conf.sh
# Then restart the nginx container:
docker restart pt-nginx1
```

````
