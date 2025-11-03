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
  - `NGINX_RATE_LIMIT_ENABLE=true|false` — Enable per-client request rate limiting (limit_req)
  - `NGINX_RATE_LIMIT_RATE` — Rate for `limit_req_zone` (e.g. `10r/s` or `100r/m`). Default: `10r/s`
  - `NGINX_RATE_LIMIT_BURST` — Burst size for `limit_req`. Default: `20`
  - `NGINX_RATE_LIMIT_ZONE_SIZE` — Shared memory zone size for `limit_req_zone` (e.g. `10m`). Default: `10m`

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

## Rate Limiting

Rate limiting protects your deployment from abuse by restricting the number of requests a single client (IP address) can make in a given time period. When a client exceeds the rate limit, their requests are queued (burst allowance) and then rejected with HTTP 503 (Service Unavailable).

### Configuration

To enable rate limiting, add the following to your `.env`:

```properties
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=10r/s          # Allow 10 requests per second per IP
NGINX_RATE_LIMIT_BURST=20             # Allow burst of up to 20 requests
NGINX_RATE_LIMIT_ZONE_SIZE=10m        # Shared memory for tracking (10MB = ~160k IPs)
```

**Parameters explained:**
- `NGINX_RATE_LIMIT_RATE`: Sets the maximum request rate (e.g., `10r/s` for 10 req/sec, `100r/m` for 100 req/min)
- `NGINX_RATE_LIMIT_BURST`: Number of requests allowed to exceed the rate before being queued/rejected
- `NGINX_RATE_LIMIT_ZONE_SIZE`: Shared memory zone size. Estimate: 1MB ≈ 16,000 client IPs

### Example Configurations

**Moderate rate limiting (recommended for most deployments):**
```properties
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=10r/s
NGINX_RATE_LIMIT_BURST=20
NGINX_RATE_LIMIT_ZONE_SIZE=10m
```

**Strict rate limiting (for high-security deployments):**
```properties
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=5r/s
NGINX_RATE_LIMIT_BURST=10
NGINX_RATE_LIMIT_ZONE_SIZE=20m
```

**Lenient rate limiting (for internal/trusted networks):**
```properties
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=50r/s
NGINX_RATE_LIMIT_BURST=100
NGINX_RATE_LIMIT_ZONE_SIZE=10m
```

**Disable rate limiting:**
```properties
NGINX_RATE_LIMIT_ENABLE=false
```

### Testing Rate Limiting

After regenerating the config and restarting nginx, you can test rate limiting using `ab` (Apache Bench) or `curl`:

**Using Apache Bench (100 requests, 10 concurrent):**
```bash
ab -n 100 -c 10 http://localhost:8000/
```

**Using curl with parallel requests:**
```bash
for i in {1..30}; do curl http://localhost:8000/ & done; wait
```

**Using nginx logs to verify:**
```bash
# Inside the nginx container:
docker exec pt-nginx1 tail -f /var/log/nginx/access.log | grep "503"
```

Clients exceeding the rate limit will see HTTP 503 responses in the logs.

### How Rate Limiting Works

1. **`limit_req_zone`** (http context): Defines a shared memory zone (`pt_req_zone`) that tracks client IPs and their request counts
2. **`limit_req`** (location block): Applies the rate limit to the location. The `nodelay` parameter causes excess requests to be rejected immediately instead of queued

When a client exceeds the rate limit:
- Requests within the burst allowance are served
- Additional requests are rejected with HTTP 503
- The client must wait before making more requests

### Combining with GeoIP Filtering

Rate limiting works independently of GeoIP filtering. If both are enabled:
1. GeoIP checks run first (allow/block countries)
2. Allowed traffic then goes through rate limiting per client IP

Example configuration with both features:
```properties
ENABLE_HTTPS=true
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=10r/s
NGINX_RATE_LIMIT_BURST=20
```

## Notes & Caveats

- The generator adds GeoIP mappings at the nginx `http` context level and filtering checks in each server block
- Rate limiting is applied per client IP (`$binary_remote_addr`) at the location level
- 444 is a special nginx response code that closes the connection without sending a response to the client
- The generator does not create certificates or download GeoIP databases; these must be provided separately
- This is a lightweight helper; production deployments should use proper templating or configuration management and ensure the nginx GeoIP module is available
- If `ENABLE_HTTPS`, `NGINX_GEOIP_ALLOW`, and `NGINX_GEOIP_BLOCK` are all disabled or country lists are empty, the generated config will be plain HTTP with no filtering
- Rate limiting zone size should be adjusted for deployments with many concurrent clients; start with 10m and increase if needed

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
