# Security Features Quick Reference

This file documents the security features added to PacketTracerWeb for production deployment.

## 🔐 Implemented Features

### 1. Automatic Credential Generation ✅

**File:** `secure-setup.sh`

Generate strong random credentials for all services:
- MariaDB root password (32 bytes)
- MariaDB user password (32 bytes)  
- VNC password (24 bytes)
- Guacamole user password (16 bytes)
- Download authentication credentials (16 bytes)

**Usage:**
```bash
bash secure-setup.sh
```

**Output:**
- `.env.secure` - Credentials stored with restricted permissions (600)
- `.env.init` - Environment variables for deploy.sh
- Credentials displayed ONE TIME ONLY (save securely!)

---

### 2. HTTPS/TLS Support ✅

**Conditional:** Optional - based on user choice during setup

**Features:**
- HTTP to HTTPS redirect
- TLS 1.2+ enforcement
- Strong cipher suites
- Session caching and OCSP stapling
- Self-signed or Let's Encrypt certificates

**Setup:**
```bash
# During secure-setup.sh, answer 'y' to HTTPS question
# Then provide certificates or generate them

# Let's Encrypt example:
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/*.pem ptweb-vnc/certs/
```

**Config Files:**
- `ptweb-vnc/pt-nginx/conf/ptweb-secure.conf` - Has HTTPS directives commented out
- Uncomment `listen 443 ssl http2;` and SSL cert paths when ready

---

### 3. GeoIP-Based Access Restrictions ✅

**Conditional:** Optional - based on user choice during setup

**Features:**
- Block access from specific countries
- Allow access only from whitelisted countries
- Uses MaxMind GeoIP2 database (free GeoLite2 or paid)
- Optional - if not configured, all countries allowed

**Setup:**
```bash
# During secure-setup.sh, answer 'y' to GeoIP question
# Enter country codes: US,GB,DE,CA

# System will create:
# ptweb-vnc/pt-nginx/conf/geoip-allowed.conf
# (Contains allow list for specified countries)
```

**Manual Configuration:**
- Download MaxMind GeoIP2 database
- Place in `ptweb-vnc/pt-nginx/conf/geoip-data/`
- Uncomment GeoIP module in nginx config
- See `GEOIP-SETUP.md` for detailed guide

**Supported Countries:**
All ISO 3166-1 alpha-2 codes (US, GB, DE, FR, CA, AU, JP, CN, etc.)

---

### 4. Download Path Authentication ✅

**Conditional:** Optional - based on user choice during setup

**Features:**
- HTTP Basic Authentication for `/downloads/` path
- Separate credentials from Guacamole login
- Rate limiting on downloads (50 req/min)
- File execution prevention (.php, .sh, .exe blocked)

**Setup:**
```bash
# During secure-setup.sh, answer 'y' to download auth question
# System will generate credentials and create .htpasswd file

# Credentials displayed:
# Username: downloader
# Password: [16-byte random]
```

**Manual Configuration:**
```bash
# Generate htpasswd file manually
mkdir -p ptweb-vnc/pt-nginx/auth
htpasswd -bc ptweb-vnc/pt-nginx/auth/.htpasswd username password

# Uncomment in ptweb-vnc/pt-nginx/conf/ptweb-secure.conf:
# auth_basic "Restricted Downloads";
# auth_basic_user_file /etc/nginx/auth/.htpasswd;
```

---

### 5. Rate Limiting ✅

**Always Enabled**

**Limits:**
- Guacamole Login: 10 requests/minute
- Guacamole API: 100 requests/minute
- Downloads: 50 requests/minute
- General: 100 requests/minute

**Config File:** `ptweb-vnc/pt-nginx/conf/ptweb-secure.conf`

**Customization:**
```nginx
limit_req_zone $binary_remote_addr zone=guac_login:10m rate=10r/m;
# Change "10r/m" to desired rate
```

---

### 6. Security Headers ✅

**Always Enabled**

**Headers Added:**
- `X-Content-Type-Options: nosniff` - Prevent MIME type sniffing
- `X-Frame-Options: SAMEORIGIN` - Prevent clickjacking
- `X-XSS-Protection: 1; mode=block` - XSS protection
- `Referrer-Policy: strict-origin-when-cross-origin` - Referrer control
- `Permissions-Policy` - Disable geolocation, microphone, camera
- `Strict-Transport-Security` - (enabled after HTTPS setup)

---

### 7. Network Isolation ✅

**For Docker Compose Secure Version**

**Features:**
- MariaDB on internal network only (port 3306 not exposed)
- Guacd on internal network only
- Only Nginx exposed to host
- Container-to-container communication only

**File:** `ptweb-vnc/docker-compose-secure.yml`

**Usage:**
```bash
# To use secure docker-compose:
# 1. Review docker-compose-secure.yml
# 2. Copy to docker-compose.yml or specify in deploy.sh
# 3. Deploy as normal
```

---

### 8. Container Security Hardening ✅

**In Docker Compose Secure Version**

**Features:**
- `cap_drop: ALL` - Drop all capabilities
- `security_opt: no-new-privileges:true` - Prevent privilege escalation
- `read_only: true` - Read-only filesystems where possible
- Health checks on all services
- Resource limits (can be configured)
- JSON logging with size limits

---

### 9. Credential Storage ✅

**Files Created by secure-setup.sh:**

- `.env.secure` (600) - All credentials
  - DO NOT commit to git
  - Store in secure vault or password manager
  - Displayed once, then hidden

- `.env.init` (600) - Environment exports for deploy.sh
  - Loaded by deployment scripts
  - Not displayed after creation

- `.gitignore` - Updated to exclude credentials
  - Prevents accidental commits

---

### 10. Logging & Monitoring ✅

**Logging Directory:** `logs/`

**Log Access:**
```bash
# Guacamole logs
docker logs pt-guacamole | grep -i "authentication\|failed"

# Nginx logs
docker logs pt-nginx1

# MariaDB logs
docker logs guacamole-mariadb

# Export logs to files
docker logs pt-guacamole >> logs/guacamole.log
docker logs pt-nginx1 >> logs/nginx.log
```

**Security Events to Monitor:**
- Failed login attempts
- Rate limit violations (429 errors)
- Blocked requests (403 errors)
- GeoIP blocks
- Authentication failures

---

## 🚀 Quick Start for Production

### Step 1: Generate Secure Config
```bash
bash secure-setup.sh
```

### Step 2: Review & Save Credentials
```bash
cat .env.secure
# Save credentials in secure location (vault, password manager, etc.)
```

### Step 3: Set Up HTTPS (Optional but Recommended)
```bash
# Let's Encrypt
sudo certbot certonly --standalone -d your-domain.com
sudo cp /etc/letsencrypt/live/your-domain.com/*.pem ptweb-vnc/certs/

# Then uncomment HTTPS in ptweb-vnc/pt-nginx/conf/ptweb-secure.conf
```

### Step 4: Set Up GeoIP (Optional)
```bash
# If you selected GeoIP during setup:
# 1. Download MaxMind GeoIP2 database
# 2. Place in ptweb-vnc/pt-nginx/conf/geoip-data/
# 3. See GEOIP-SETUP.md for details
```

### Step 5: Deploy
```bash
bash deploy.sh
```

### Step 6: Verify
```bash
bash test-deployment.sh
```

---

## 🔒 Environment Variable Reference

All options set during `secure-setup.sh`:

```bash
# Database
DB_ROOT_PASSWORD=<32-byte random>
DB_NAME=guacamole_db
DB_USER=ptdbuser
DB_USER_PASSWORD=<32-byte random>
DB_PORT=3306

# VNC
VNC_PASSWORD=<24-byte random>
VNC_RESOLUTION=1024x768

# Guacamole
GUACAMOLE_USERNAME=ptadmin
GUACAMOLE_PASSWORD=<16-byte random>

# Network
NGINX_PORT=80
NGINX_SSL_PORT=443
GUACAMOLE_PORT=8080

# Security Features
ENABLE_HTTPS=true|false
ENABLE_GEOIP=true|false
ALLOWED_COUNTRIES=US,GB,DE,...
REQUIRE_DOWNLOAD_AUTH=true|false
DOWNLOAD_AUTH_USER=downloader
DOWNLOAD_AUTH_PASSWORD=<16-byte random>
```

---

## 📚 Related Documentation

- `SECURITY.md` - Comprehensive security guide
- `GEOIP-SETUP.md` - Detailed GeoIP configuration
- `README.md` - General deployment guide
- `TEST-DEPLOYMENT.md` - Health check procedures

---

## ✅ Checklist for Public Internet Deployment

- [ ] Run `bash secure-setup.sh` with all security options enabled
- [ ] Save credentials in secure location (not in git)
- [ ] Set up HTTPS with valid certificates
- [ ] Configure GeoIP restrictions if needed
- [ ] Enable download authentication
- [ ] Review nginx config for security headers
- [ ] Set up centralized logging
- [ ] Run `bash test-deployment.sh` to verify
- [ ] Configure firewall rules (allow only 80/443)
- [ ] Set up monitoring and alerts
- [ ] Document procedures for staff
- [ ] Schedule regular security updates
- [ ] Plan credential rotation (quarterly minimum)

---

**Last Updated:** October 31, 2025  
**Status:** Production Ready ✅
