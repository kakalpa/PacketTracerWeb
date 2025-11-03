# Packet Tracer - Web-Based Multi-Instance Deployment

Run multiple Cisco Packet Tracer instances in Docker containers with web-based access via Guacamole.  
Includes **GeoIP filtering** and **rate limiting** for security.  
Inspired by this original project [[ptremote](https://github.com/cnkang/ptremote)]

## 🚀 Quick Start

### Prerequisites
- Linux system with Docker installed
- Cisco Packet Tracer `.deb` installer (v9+)
- 4GB+ RAM available

### Installation

#### Version 2.1 (Current) - With Rate Limiting & Enhanced Security
```bash
# 1. Clone the repository (latest version with GeoIP + Rate Limiting)
git clone https://github.com/kakalpa/PacketTracerWeb.git
cd PacketTracerWeb

# 2. Place Packet Tracer .deb file in repo root
# (deploy.sh will automatically build the Docker image)

# 3. (Optional) Configure GeoIP, Rate Limiting or HTTPS in .env
# See configuration sections below for options

# 4. Run deployment
bash deploy.sh

# This will automatically:
# - Generate nginx configuration (with GeoIP and Rate Limiting if configured)
# - Download GeoIP database (if GeoIP filtering enabled)
# - Build the ptvnc Docker image (first time only)
# - Start MariaDB container
# - Start 2 Packet Tracer VNC containers
# - Configure Guacamole web interface
# - Generate web access endpoints
# - Mount GeoIP database (if available)
# - Apply rate limiting rules (if enabled)

# 5. Open browser
http://localhost/

# 6. Login: ptadmin / IlovePT

# 7. Click connection (pt01, pt02, etc.) to access instance
```

#### Version 2.0 - With GeoIP Support
```bash
# Clone version 2.0 (with GeoIP, without rate limiting)
git clone --branch v2.0 https://github.com/kakalpa/PacketTracerWeb.git
cd PacketTracerWeb

# Place Packet Tracer .deb in repo root
# Configure GeoIP or HTTPS in .env

# Run deployment
bash deploy.sh
```

#### Version 1.0 (Without GeoIP) - Legacy Release
If you prefer the version without GeoIP filtering capabilities, use v1.0:
```bash
# Clone version 1.0 (legacy, without GeoIP database support)
git clone --branch v1.0 https://github.com/kakalpa/PacketTracerWeb.git
cd PacketTracerWeb

# Place Packet Tracer .deb in repo root
# Configure optional HTTPS in .env

# Run deployment
bash deploy.sh

# This will deploy with basic setup (no GeoIP filtering)
```

**Differences between versions:**
| Feature | v2.1 (Current) | v2.0 | v1.0 (Legacy) |
|---------|---|---|---|
| **GeoIP Database** | ✅ Automatic | ✅ Automatic | ❌ Manual setup |
| **GeoIP Filtering** | ✅ Allowlist/Blocklist | ✅ Allowlist/Blocklist | ⚠️ Requires manual config |
| **Rate Limiting** | ✅ Per-IP request limiting | ❌ Not available | ❌ Not available |
| **Nginx** | ✅ Custom image with GeoIP module | ✅ Custom image with GeoIP module | ✅ Standard nginx |
| **HTTPS Support** | ✅ Yes | ✅ Yes | ✅ Yes |
| **Maintenance** | ✅ Latest features & security | ⚠️ Security fixes only | ⚠️ No updates |

---

## 🌍 GeoIP Filtering (NEW)

The deployment now supports **automatic GeoIP configuration** integrated into `deploy.sh`. No separate scripts needed!

### Quick Setup

#### Enable Allowlist (Whitelist - Only allow specific countries)
```bash
# In .env file:
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU

bash deploy.sh
```
✅ Users from US, Canada, GB, Australia can access
❌ All other countries get connection closed (no response sent)

#### Enable Blocklist (Blacklist - Block specific countries)
```bash
# In .env file:
NGINX_GEOIP_BLOCK=true
GEOIP_BLOCK_COUNTRIES=CN,RU,IR

bash deploy.sh
```
✅ All users allowed except those from China, Russia, Iran
❌ Listed countries get connection closed

#### Enable HTTPS with GeoIP
```bash
# In .env file:
ENABLE_HTTPS=true
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA
SSL_CERT_PATH=/etc/ssl/certs/ssl-cert.pem
SSL_KEY_PATH=/etc/ssl/private/ssl-key.pem

bash deploy.sh
```

### How It Works

1. **deploy.sh reads .env** for GeoIP settings
2. **Nginx config is generated automatically** with GeoIP directives
3. **GeoIP database is downloaded** (from DB-IP)
4. **Database is mounted** into nginx container
5. **Filtering starts immediately** on deployment

## 🔔 Recent: GeoIP & nginx changes + Fixed add/remove instance scripts

### Nginx & GeoIP Setup
- Custom `pt-nginx` image built with HTTP GeoIP module enabled (replaces standard nginx)
- Complete `nginx.conf`/`ptweb.conf` generated at build/deploy time (no runtime injection)
- `deploy.sh` detects Guacamole IP and substitutes into `ptweb.conf` for correct `proxy_pass`
- GeoIP database (GeoIP.dat / GeoIPv6.dat) auto-downloaded and mounted when filtering enabled
- By default permissive (allow all) - explicitly enable ALLOW or BLOCK modes in `.env`
- Private/local IP ranges exempted from GeoIP checks

### Fixed: add-instance.sh & remove-instance.sh
- Both scripts now use custom `pt-nginx` image (was using standard `nginx`, causing config errors)
- Scripts correctly restart nginx with GeoIP support when adding/removing instances
- All services properly linked and reconnected during scaling operations

### Configuration Options

| Setting | Values | Purpose |
|---------|--------|---------|
| `NGINX_GEOIP_ALLOW` | `true/false` | Enable whitelist mode (allow only specified countries) |
| `GEOIP_ALLOW_COUNTRIES` | Country codes | Comma-separated list (e.g., `US,CA,GB`) |
| `NGINX_GEOIP_BLOCK` | `true/false` | Enable blacklist mode (block specified countries) |
| `GEOIP_BLOCK_COUNTRIES` | Country codes | Comma-separated list (e.g., `CN,RU,IR`) |
| `NGINX_RATE_LIMIT_ENABLE` | `true/false` | Enable per-IP request rate limiting |
| `NGINX_RATE_LIMIT_RATE` | Rate string | Rate limit (e.g., `10r/s`, `100r/m`) |
| `NGINX_RATE_LIMIT_BURST` | Integer | Burst allowance (default: 20) |
| `NGINX_RATE_LIMIT_ZONE_SIZE` | Size string | Memory zone size (e.g., `10m`, `20m`) |
| `ENABLE_HTTPS` | `true/false` | Enable HTTPS with auto-redirect |
| `SSL_CERT_PATH` | Path | Container path to certificate (e.g., `/etc/ssl/certs/ssl-cert.pem`) |
| `SSL_KEY_PATH` | Path | Container path to private key (e.g., `/etc/ssl/private/ssl-key.pem`) |

### Priority & Defaults

- If `NGINX_GEOIP_ALLOW=true`, it takes precedence over BLOCK mode
- If countries list is empty, filtering is skipped for that mode
- If both are `false`, no GeoIP filtering is applied
- GeoIP database is only downloaded if ALLOW or BLOCK mode is enabled
- GeoIP database location: `./geoip/GeoIP.dat` (gitignored, not committed)

### GeoIP Database

- **Source:** MaxMind GeoLite2 (public, no authentication required)
- **Format:** Binary GeoIP country database
- **License:** CC BY-SA 4.0 (free & open)
- **Accuracy:** ~99% country-level accuracy
- **Size:** ~2MB compressed, ~20MB uncompressed
- **Auto-Download:** `deploy.sh` downloads if not present
- **Location:** `./geoip/GeoIP.dat` (local), `/usr/share/GeoIP/GeoIP.dat` (in container)

### Troubleshooting GeoIP

**GeoIP filtering not working?**
```bash
# Check if GeoIP database was downloaded
ls -lh ./geoip/GeoIP.dat

# View generated nginx config
cat ptweb-vnc/pt-nginx/conf/ptweb.conf

# Restart nginx with new config
docker restart pt-nginx1
```

**Download failed during deploy?**
```bash
# Manual download
mkdir -p ./geoip
wget -O ./geoip/GeoIP.dat.gz \
  "https://geolite.maxmind.com/download/geoip/database/GeoLiteCountry/GeoIP.dat.gz"
gunzip ./geoip/GeoIP.dat.gz

# Re-run deploy
bash deploy.sh
```

---

## � HTTPS/SSL (Optional)

Enable secure connections with a simple flag:

```bash
# In .env file:
ENABLE_HTTPS=true

bash deploy.sh
```

**What happens:**
- ✅ HTTPS server listens on port 443
- ✅ HTTP requests auto-redirect to HTTPS (301)
- ✅ Self-signed certificate in `./ssl/` directory

**Generate new certificate (if needed):**
```bash
bash generate-ssl-cert.sh
```

**Disable HTTPS:**
```bash
# In .env file:
ENABLE_HTTPS=false

bash deploy.sh
```

---

## 🚦 Rate Limiting (New!)

Protect your deployment from brute-force attacks and DoS with per-IP request rate limiting.

### Quick Enable

```bash
# In .env file:
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=10r/s        # 10 requests/second per IP
NGINX_RATE_LIMIT_BURST=20          # Allow burst of 20 requests
NGINX_RATE_LIMIT_ZONE_SIZE=10m     # Support ~160k unique IPs

bash deploy.sh
```

### Testing Rate Limiting

```bash
# Send 50 rapid requests (will show mix of 200 and 503)
for i in {1..50}; do curl -k https://localhost/ 2>/dev/null & done; wait

# Monitor for 503 (rate-limited) responses
docker exec pt-nginx1 tail -f /var/log/nginx/access.log | grep " 503 "

# Run validation test
bash test-rate-limiting.sh
```



---

## �📝 Available Scripts

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Initial deployment (2 instances, auto-setup GeoIP/HTTPS if configured) |
| `add-instance.sh` | Add new instances dynamically |
| `remove-instance.sh` | Remove instances safely |
| `tune_ptvnc.sh` | Adjust CPU/memory per container |
| `generate-dynamic-connections.sh` | Regenerate Guacamole database connections |
| `health_check.sh` | Comprehensive health check (41 tests) |

### Automatic Image Building

`deploy.sh` and `add-instance.sh` automatically build the `ptvnc` Docker image if it doesn't exist:
- ✅ First deployment: Image is built automatically
- ✅ After cloning repo: Image is built on first run
- ✅ After removing images: Image rebuilds automatically
- ✅ Subsequent runs: Uses cached image (much faster)

---

## 💾 Downloading Files (Web-Based)

Users work entirely within the web interface. To download Packet Tracer files:

### Easy Method: Shared Folder (Desktop Shortcut)
1. **On the desktop**, you'll see a **"shared"** folder
2. **Inside Packet Tracer:**
   - File → Save As
   - Navigate to the **"shared"** folder on desktop
   - Save your file (e.g., `mynetwork.pkt`)

3. **Download from browser:**
   - Go to: `http://localhost/downloads/`
   - Files appear automatically after saving
   - Click file to download

### Alternative Method: Direct Path
- File → Save As → `/shared/mynetwork.pkt`
- Then visit `http://localhost/downloads/` <== trailing / is required ! 

## 🎯 Usage Examples

### Deploy (2 instances)
```bash
bash deploy.sh
# Creates: pt01, pt02
```
initial deployment might take upto 5-6 minutes. be patient 😉

### Recreate/Reset Deployment (Clean slate)
```bash
bash deploy.sh recreate
# Removes ALL containers and volumes, then deploys fresh stack
# Useful for testing or when you want a completely clean environment
```
This command will:
- ✅ Remove all Packet Tracer containers (ptvnc1, ptvnc2, ...)
- ✅ Remove all Guacamole containers (guacamole-mariadb, pt-guacd, pt-guacamole, pt-nginx1)
- ✅ Remove all Docker volumes (clean slate data)
- ✅ Clear GeoIP database cache (will re-download on next deploy if configured)

- ✅ Then deploy fresh 2-instance stack

⚠️ **Note:** This removes all data. Save important files to `/shared/` before running!

### Add Instances
```bash
bash add-instance.sh      # Add 1 more instance (pt03 if you have pt01, pt02)
bash add-instance.sh 2    # Add 2 more instances
bash add-instance.sh 5    # Add 5 more instances
```
Automatically restarts services and updates web interface.

### Remove Instances
```bash
# Remove by count (highest numbered instances first)
bash remove-instance.sh   # Remove 1 instance (pt05)
bash remove-instance.sh 2 # Remove 2 instances (pt05, pt04)
bash remove-instance.sh 3 # Remove 3 instances (pt05, pt04, pt03)

# Remove specific instances by name
bash remove-instance.sh pt02          # Remove pt02 only
bash remove-instance.sh pt01 pt03     # Remove pt01 and pt03
bash remove-instance.sh pt02 pt04 pt05 # Remove multiple specific instances
```
⚠️ **Warning:** Active users will be disconnected during removal. Always save work to `/shared/` beforehand.

### Tune Performance
```bash
bash tune_ptvnc.sh 2G 1   # 2GB RAM, 1 CPU per container
bash tune_ptvnc.sh 4G 2   # 4GB RAM, 2 CPUs per container
```

### Regenerate Connections (if needed)
```bash
bash generate-dynamic-connections.sh 3
```

---

### ✅ Testing Deployment Health

After deployment, verify everything is working with the comprehensive test suite:

```bash
bash health_check.sh
```

This runs **57 tests** across 12 categories and displays configuration status:
- **GeoIP Tests:** Enabled/Disabled (based on `.env`)
- **HTTPS:** Enabled/Disabled (based on `ENABLE_HTTPS` setting)
1. **Docker Containers** - Verify all 6 containers are running
2. **Database Connectivity** - Test MariaDB and Guacamole DB
3. **Shared Folder** - Verify `/shared/` mounted in all containers
4. **Write Permissions** - Test file creation in `/shared/`
5. **Desktop Symlinks** - Check shortcuts on desktop
6. **Web Endpoints** - Test Guacamole and `/downloads/` access
7. **File Download Workflow** - End-to-end file save/download cycle
8. **Helper Scripts** - Verify all utilities exist
9. **Docker Volumes** - Check persistent storage
10. **Database Schema** - Validate Guacamole tables
11. **Docker Networking** - Test container communication
12. **GeoIP Configuration** - Verify module, database, and filtering (if enabled)

**Expected Output:** ✅ All 57 tests pass

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Container name conflict | `docker rm -f <container_name>` |
| Connections not showing | `bash generate-dynamic-connections.sh <count>` |
| Slow performance | `bash tune_ptvnc.sh 2G 1` |
| Tests failing | `bash health_check.sh` to identify issues |

---

## 📄 License

Cisco Packet Tracer installer not included. Place official copy in repo root. Using Packet Tracer implies acceptance of Cisco EULA.
