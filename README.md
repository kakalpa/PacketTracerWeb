# Packet Tracer - Web-Based Multi-Instance Deployment

Run multiple Cisco Packet Tracer instances in Docker containers with web-based access via Guacamole.  
Includes **GeoIP filtering**, **rate limiting**, and **HTTPS support**.

---

## 🚀 Quick Start

### Prerequisites
- Linux system with Docker installed
- Cisco Packet Tracer `.deb` installer (v9+)
- 4GB+ RAM available

### Installation (3 Steps)

```bash
# 1. Clone repository
git clone https://github.com/kakalpa/PacketTracerWeb.git
cd PacketTracerWeb

# 2. Place Packet Tracer .deb file in repo root
# (The .deb file is required for deployment)

# 3. Deploy
bash deploy.sh

# Opens browser at: http://localhost/
# Login: ptadmin / IlovePT
```

⏱️ **First deployment takes 5-6 minutes** (includes Docker image build)

---

## ✨ Key Features

| Feature | Status | Details |
|---------|--------|---------|
| **Multi-Instance** | ✅ | Deploy 2+ Packet Tracer instances |
| **Web Access** | ✅ | Guacamole web UI (no client install needed) |
| **GeoIP Filtering** | ✅ | Whitelist/Blacklist countries |
| **Rate Limiting** | ✅ | Per-IP request limits (DDoS protection) |
| **HTTPS/SSL** | ✅ | Secure connections with auto-redirect |
| **File Downloads** | ✅ | Save files from Packet Tracer to browser |
| **Auto-Scaling** | ✅ | Add/remove instances on-the-fly |
| **Health Monitoring** | ✅ | Built-in health check suite |

---

## � Common Commands

### Deploy & Manage

```bash
# Initial deployment (2 instances)
bash deploy.sh

# Clean redeploy (removes all containers/volumes)
bash deploy.sh recreate

# Add instances
bash add-instance.sh      # Add 1
bash add-instance.sh 5    # Add 5

# Remove instances
bash remove-instance.sh   # Remove 1
bash remove-instance.sh 2 # Remove 2

# Tune performance (RAM, CPU per container)
bash tune_ptvnc.sh 2G 1   # 2GB RAM, 1 CPU
```

### Test & Verify

```bash
# Full health check (57 tests)
bash health_check.sh

# View logs
docker logs pt-nginx1
docker logs pt-guacamole
```

---

## ⚙️ Configuration

Edit `.env` file before running `bash deploy.sh`:

### GeoIP Filtering (Optional)

```env
# Whitelist mode: Only allow these countries
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU

# Blacklist mode: Block these countries
NGINX_GEOIP_BLOCK=true
GEOIP_BLOCK_COUNTRIES=CN,RU,IR

# Production mode: Auto-detect public IP and add to trusted list
PRODUCTION_MODE=true
```

### HTTPS/SSL (Optional)

```env
ENABLE_HTTPS=true
SSL_CERT_PATH=/etc/ssl/certs/server.crt
SSL_KEY_PATH=/etc/ssl/private/server.key

# Generate certificates:
bash generate-ssl-cert.sh
```

### Rate Limiting (Optional)

```env
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=100r/s
NGINX_RATE_LIMIT_BURST=200
NGINX_RATE_LIMIT_ZONE_SIZE=10m
```

---

## 💾 Downloading Files

Users can save and download Packet Tracer files:

1. **Inside Packet Tracer:** File → Save As → Navigate to **"shared"** folder on desktop
2. **Download from browser:** Visit `http://localhost/downloads/`
3. **Files appear automatically** after saving from Packet Tracer

---

## 🌍 GeoIP Filtering (Details)

The deployment now supports **automatic GeoIP configuration** integrated into `deploy.sh`. No separate scripts needed!

### Enable Allowlist (Whitelist)
```bash
# In .env file:
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU

bash deploy.sh
```
✅ Users from specified countries can access  
❌ All other countries get connection closed

### Enable Blocklist (Blacklist)
```bash
# In .env file:
NGINX_GEOIP_BLOCK=true
GEOIP_BLOCK_COUNTRIES=CN,RU,IR

bash deploy.sh
```
✅ All users allowed except listed countries  
❌ Listed countries get connection closed

### How It Works

1. **deploy.sh reads .env** for GeoIP settings
2. **Nginx config is generated automatically** with GeoIP directives
3. **GeoIP database is downloaded** (from MaxMind)
4. **Database is mounted** into nginx container
5. **Filtering starts immediately** on deployment

### GeoIP Database Info

- **Source:** MaxMind GeoLite2 (public, free)
- **License:** CC BY-SA 4.0
- **Accuracy:** ~99% country-level
- **Size:** ~20MB uncompressed
- **Auto-Download:** `deploy.sh` handles it
- **Location:** `./geoip/GeoIP.dat`

### Quick Enable

```bash
# In .env file:
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=100r/s
NGINX_RATE_LIMIT_BURST=200

bash deploy.sh
```

Protects against brute-force and DDoS attacks with per-IP request limits.

---

## � Project Structure

```
PacketTracerWeb/
├── deploy.sh                           # Main deployment script
├── add-instance.sh                     # Add instances
├── remove-instance.sh                  # Remove instances
├── tune_ptvnc.sh                       # Performance tuning
├── generate-dynamic-connections.sh     # Regenerate connections
├── generate-ssl-cert.sh                # Generate SSL certs
├── health_check.sh                     # 57 health tests
├── test-deployment.sh                  # Full test suite
├── README.md                           # This file
├── .env                                # Configuration
│
├── Scripts/                            # Test scripts
├── ptweb-vnc/                          # Docker image (Packet Tracer)
├── shared/                             # User files (bind-mounted)
└── geoip/                              # GeoIP database (auto-downloaded)
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Port already in use** | `docker ps` to see running containers; `docker stop <name>` |
| **Connections not showing** | `bash generate-dynamic-connections.sh 2` |
| **Slow performance** | `bash tune_ptvnc.sh 4G 2` (increase RAM/CPU) |
| **Tests failing** | `bash health_check.sh` to diagnose |
| **GeoIP not working** | Check `.env` settings; verify `geoip/GeoIP.dat` exists |
| **HTTPS certificate errors** | Run `bash generate-ssl-cert.sh` to regenerate |

---

## 📚 Documentation

Detailed documentation available in `Documents/` folder (for your reference).

Test scripts and validation: See `Scripts/README.md`

---

## 📄 License

Cisco Packet Tracer installer not included. Place official `.deb` copy in repo root.  
Using Packet Tracer implies acceptance of Cisco EULA.

---

## 🔗 References

Original project: [ptremote](https://github.com/cnkang/ptremote)  
Docker documentation: [docker.com](https://docker.com)  
Guacamole: [guacamole.apache.org](https://guacamole.apache.org)
```
├── .env                                # Configuration
│
├── Scripts/                            # Test scripts
├── ptweb-vnc/                          # Docker image (Packet Tracer)
├── shared/                             # User files (bind-mounted)
└── geoip/                              # GeoIP database (auto-downloaded)
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| **Port already in use** | `docker ps` to see running containers; `docker stop <name>` |
| **Connections not showing** | `bash generate-dynamic-connections.sh 2` |
| **Slow performance** | `bash tune_ptvnc.sh 4G 2` (increase RAM/CPU) |
| **Tests failing** | `bash health_check.sh` to diagnose |
| **GeoIP not working** | Check `.env` settings; verify `geoip/GeoIP.dat` exists |
| **HTTPS certificate errors** | Run `bash generate-ssl-cert.sh` to regenerate |

---

## 📚 Documentation

Detailed documentation available in `Documents/` folder (for your reference).

Test scripts and validation: See `Scripts/README.md`

---

## 📄 License

Cisco Packet Tracer installer not included. Place official `.deb` copy in repo root.  
Using Packet Tracer implies acceptance of Cisco EULA.

---

## 🔗 References

Original project: [ptremote](https://github.com/cnkang/ptremote)  
Docker documentation: [docker.com](https://docker.com)  
Guacamole: [guacamole.apache.org](https://guacamole.apache.org)

---

## 📖 Documentation

All documentation is organized in the `Documents/` folder:

| Document | Purpose |
|----------|---------|
| **Documents/GEOIP-FIX-SUMMARY.md** ⭐ | Quick reference for GeoIP fixes (start here) |
| **Documents/VPS-DEPLOYMENT-GUIDE.md** ⭐ | Step-by-step VPS deployment instructions |
| **Documents/COMPREHENSIVE_DOCUMENTATION.md** | Full architecture and configuration guide |
| **Documents/GEOIP-FIX-TEST-REPORT.md** | Detailed testing results and validation |
| **Documents/README.md** | Navigation guide for all documentation |

- **Test Documentation:** `Scripts/README.md` (explains all test scripts)

---

## 🐛 Troubleshooting

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
```

**📌 Key Files:**
- **Deployment:** `deploy.sh` (main entry point)
- **Configuration:** `.env` (environment variables)
- **Testing:** `test-deployment.sh` (full suite), `Scripts/test-*.sh` (unit tests)
- **Test Documentation:** `Scripts/README.md` (explains all test scripts)

---

## 📖 Documentation

All documentation is organized in the `Documents/` folder:

| Document | Purpose |
|----------|---------|
| **Documents/GEOIP-FIX-SUMMARY.md** ⭐ | Quick reference for GeoIP fixes (start here) |
| **Documents/VPS-DEPLOYMENT-GUIDE.md** ⭐ | Step-by-step VPS deployment instructions |
| **Documents/COMPREHENSIVE_DOCUMENTATION.md** | Full architecture and configuration guide |
| **Documents/GEOIP-FIX-TEST-REPORT.md** | Detailed testing results and validation |
| **Documents/README.md** | Navigation guide for all documentation |

- **Test Documentation:** `Scripts/README.md` (explains all test scripts)

---

## 🐛 Troubleshooting

---

## �🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Container name conflict | `docker rm -f <container_name>` |
| Connections not showing | `bash generate-dynamic-connections.sh <count>` |
| Slow performance | `bash tune_ptvnc.sh 2G 1` |
| Tests failing | `bash health_check.sh` to identify issues |

---

## 📄 License

Cisco Packet Tracer installer not included. Place official copy in repo root. Using Packet Tracer implies acceptance of Cisco EULA.
