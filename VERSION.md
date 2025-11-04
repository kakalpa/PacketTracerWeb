# Version Information

## Current Version: 2.1

### Latest Release
- **Version**: 2.1
- **Release Date**: November 3, 2025
- **Tag**: v2.1
- **Branch**: main

### Key Features
- ✅ **Rate Limiting**: Per-IP request rate limiting (10r/s default, configurable)
- ✅ **GeoIP Filtering**: Automatic country-based access control
- ✅ **HTTPS/SSL**: Secure connections with auto-redirect
- ✅ **Multi-Instance**: Deploy multiple PacketTracer instances
- ✅ **Web Interface**: Guacamole-based remote access
- ✅ **File Sharing**: Built-in shared folder with desktop shortcuts
- ✅ **Auto Scaling**: Add/remove instances dynamically

### System Requirements
- Linux system with Docker installed
- Cisco Packet Tracer v9+ .deb installer
- 4GB+ RAM minimum
- 2GB+ free disk space

### Getting Started

#### Quick Clone (Latest Version 2.1)
```bash
git clone https://github.com/kakalpa/PacketTracerWeb.git
cd PacketTracerWeb
bash deploy.sh
```

#### Specific Version Clone
```bash
# Version 2.1 (Current - with rate limiting)
git clone --branch v2.1 https://github.com/kakalpa/PacketTracerWeb.git

# Version 2.0 (with GeoIP, without rate limiting)
git clone --branch v2.0 https://github.com/kakalpa/PacketTracerWeb.git

# Version 1.0 (Legacy - basic setup)
git clone --branch v1.0 https://github.com/kakalpa/PacketTracerWeb.git
```

### Version History

| Version | Release Date | Features | Status |
|---------|---|---|---|
| 2.1 | Nov 3, 2025 | Rate Limiting + GeoIP + HTTPS | ✅ Current |
| 2.0 | Jul 15, 2025 | GeoIP + HTTPS | ✅ Supported |
| 1.0 | Jan 2024 | Basic Setup | ⚠️ Legacy |

### Upgrade Path
- From v2.0 → v2.1: Automatic (just `git pull`)
- From v1.0 → v2.1: Recommended for new deployments
- Backward compatible: Old config files work with new versions

### Configuration
All versions support `.env` file configuration:
```bash
# Rate Limiting (v2.1+)
NGINX_RATE_LIMIT_ENABLE=true
NGINX_RATE_LIMIT_RATE=10r/s

# GeoIP Filtering (v2.0+)
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB

# HTTPS (all versions)
ENABLE_HTTPS=true
```

### Support & Documentation
- **README.md**: Comprehensive usage guide
- **Scripts/**: Test and verification scripts
- **health_check.sh**: Deployment verification (57 tests)
- **ptweb-vnc/pt-nginx/README.md**: Nginx configuration details

### License
Cisco Packet Tracer installer not included. See LICENSE file for details.
