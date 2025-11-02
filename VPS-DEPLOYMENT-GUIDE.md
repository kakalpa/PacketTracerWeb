# VPS Deployment Guide for PacketTracerWeb v2.0.1+

## Overview

This guide explains how to deploy PacketTracerWeb on a public VPS with GeoIP filtering enabled.

**Key Features:**
- ✅ Automatic public IP detection
- ✅ Localhost and private IPs always allowed
- ✅ GeoIP whitelist/blacklist with trusted IP bypass
- ✅ HTTPS support
- ✅ Fully automated one-command deployment

---

## Quick Start (VPS)

### Prerequisites
- Ubuntu 22.04+ or similar Linux distro
- Docker and Docker Compose installed
- Cisco Packet Tracer `.deb` file in repo root
- SSH access to your VPS

### Step 1: SSH into VPS and Clone Repository

```bash
ssh user@67.172.37.62

# Clone or navigate to repo
cd /path/to/PacketTracerWeb

# Pull latest code with GeoIP fixes
git pull origin main
```

### Step 2: Configure for Production

Edit `.env` file:

```bash
# For auto-detection of public IP:
PRODUCTION_MODE=true
PUBLIC_IP=

# Enable GeoIP whitelist
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,FI

# Or manually specify public IP:
PRODUCTION_MODE=true
PUBLIC_IP=67.172.37.62
```

### Step 3: Deploy

```bash
# Full fresh deployment (cleans up old containers)
bash deploy.sh recreate

# Or incremental deployment (keeps existing containers)
bash deploy.sh
```

**What happens:**
1. GeoIP database is automatically downloaded (7.2M)
2. Public IP is auto-detected and added to trusted list
3. Docker images are built
4. All services start (MariaDB, Guacamole, Nginx, Packet Tracer containers)
5. Deployment completes in 2-3 minutes

### Step 4: Verify Deployment

```bash
# Run full test suite (57 tests)
bash test-deployment.sh

# Expected output:
# ✅ Guacamole root endpoint (HTTP 200) - PASS
# ✅ Downloads endpoint (HTTP 200) - PASS
# ✅ GeoIP Database mounted - PASS
# ... (54 more tests)
```

---

## Configuration Options

### `PRODUCTION_MODE` (true/false)

**false (default - Development):**
- Only localhost (127.x) and private IPs (10.x, 172.16-31.x, 192.168.x) allowed
- GeoIP filtering still applies to other IPs
- Good for local testing

**true (Production):**
- Auto-detects VPS public IP and adds to trusted list
- Localhost and private IPs still allowed
- VPS can access its own Guacamole interface
- GeoIP filtering applies to external users

### `PUBLIC_IP` (optional)

Manually specify the VPS public IP instead of auto-detecting:

```bash
PRODUCTION_MODE=true
PUBLIC_IP=67.172.37.62
```

If not provided and `PRODUCTION_MODE=true`, it's auto-detected via `ifconfig.co`.

### GeoIP Filtering

**Whitelist Mode (Allow specific countries):**
```bash
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,FI
```

**Blacklist Mode (Block specific countries):**
```bash
NGINX_GEOIP_BLOCK=true
GEOIP_BLOCK_COUNTRIES=CN,RU,IR
```

**Trusted IPs (bypass filtering):**
- Always: `127.x`, `10.x`, `172.16-31.x`, `192.168.x`
- Production: + your VPS public IP
- Custom override:
  ```bash
  NGINX_TRUSTED_IPS_OVERRIDE="127.0.0.1,10.0.0.0/8,203.0.113.1"
  ```

---

## Access the System

Once deployed, access via:

```bash
# HTTP (port 80)
http://67.172.37.62

# HTTPS (port 443) - if ENABLE_HTTPS=true
https://67.172.37.62

# Default Guacamole credentials (if using DB dump):
# Username: guacadmin
# Password: guacadmin
```

---

## Monitoring and Troubleshooting

### Check Container Status

```bash
# All containers
docker ps

# Specific service
docker logs pt-nginx1
docker logs pt-guacamole
docker logs pt-guacd
docker logs guacamole-mariadb

# Nginx config
docker exec pt-nginx1 nginx -t

# GeoIP database in container
docker exec pt-nginx1 ls -lh /usr/share/GeoIP/
```

### Test GeoIP Filtering

From VPS (should work):
```bash
curl -v http://localhost
# Expected: HTTP 200
```

From external IP in allowed countries (should work):
```bash
# From US IP
curl -H "X-Forwarded-For: 8.8.8.8" http://67.172.37.62
# Expected: HTTP 200
```

From external IP in blocked countries (should fail):
```bash
# From China IP
curl -H "X-Forwarded-For: 202.106.0.20" http://67.172.37.62
# Expected: HTTP 444 (connection refused)
```

### Debug GeoIP

```bash
# Check nginx config has GeoIP directives
docker exec pt-nginx1 grep "geoip_country" /etc/nginx/nginx.conf

# Check if country mappings are defined
docker exec pt-nginx1 grep -A 5 "map.*allowed_country" /etc/nginx/nginx.conf

# View nginx error logs
docker logs pt-nginx1 | grep -i "geoip\|error"
```

---

## Common Issues and Fixes

### Issue: Guacamole endpoint returns HTTP 444 (blocked)

**Cause:** VPS public IP not recognized as trusted

**Fix:**
```bash
# Option 1: Enable PRODUCTION_MODE (auto-detects IP)
PRODUCTION_MODE=true

# Option 2: Manually add VPS IP
PRODUCTION_MODE=true
PUBLIC_IP=67.172.37.62

# Then redeploy
bash deploy.sh recreate
```

### Issue: Test-deployment.sh reports "GeoIP filtering may not be enforced"

**Cause:** GeoIP database or filtering logic issue

**Fix:**
```bash
# Verify GeoIP.dat exists
ls -lh geoip/GeoIP.dat

# Check if mounted in container
docker exec pt-nginx1 test -f /usr/share/GeoIP/GeoIP.dat && echo "OK" || echo "MISSING"

# Verify nginx config syntax
docker exec pt-nginx1 nginx -t

# Restart nginx
docker restart pt-nginx1
```

### Issue: Public IP detection fails (ifconfig.co unreachable)

**Workaround:** Manually specify IP

```bash
# In .env:
PRODUCTION_MODE=true
PUBLIC_IP=67.172.37.62

# Then redeploy
bash deploy.sh recreate
```

---

## File Locations

| What | Location |
|------|----------|
| GeoIP Database | `./geoip/GeoIP.dat` |
| Shared Files | `./shared/` |
| Nginx Config | `./ptweb-vnc/pt-nginx/conf/ptweb.conf` |
| SSL Certificates | `./ssl/server.crt`, `./ssl/server.key` |
| Configuration | `./.env` |

---

## Production Checklist

Before going live:

- [ ] Clone repo: `git clone https://github.com/kakalpa/PacketTracerWeb.git`
- [ ] Copy Packet Tracer `.deb` to repo root
- [ ] Edit `.env` with production settings:
  - [ ] `PRODUCTION_MODE=true`
  - [ ] `NGINX_GEOIP_ALLOW=true` (or BLOCK mode)
  - [ ] Set countries: `GEOIP_ALLOW_COUNTRIES=...`
  - [ ] Optionally add: `ENABLE_HTTPS=true`
- [ ] Run: `bash deploy.sh recreate`
- [ ] Wait for deployment to complete (2-3 minutes)
- [ ] Run: `bash test-deployment.sh` (all 57 tests should pass)
- [ ] Access via browser: `http://67.172.37.62`
- [ ] Verify Guacamole loads without HTTP 444 errors

---

## Scaling and Advanced

### Add More Packet Tracer Instances

```bash
# Add 3 more instances (total 5)
bash add-instance.sh 5

# Or remove instances
bash remove-instance.sh 2
```

### Tune Performance

```bash
# Adjust CPU/Memory limits
bash tune_ptvnc.sh --cpus 0.5 --memory 2G
```

### Update Allowed Countries

Edit `.env`:
```bash
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,FI,DE,NL
```

Then regenerate config (without full redeploy):
```bash
docker restart pt-nginx1
```

---

## Documentation

- See `README.md` for general overview
- See `COMPREHENSIVE_DOCUMENTATION.md` for detailed architecture
- See `TEST-DEPLOYMENT.md` for testing details

## Support

For issues or questions:
1. Check logs: `docker logs <container_name>`
2. Run diagnostics: `bash test-deployment.sh`
3. Review this guide's troubleshooting section
4. Check GitHub issues: github.com/kakalpa/PacketTracerWeb
