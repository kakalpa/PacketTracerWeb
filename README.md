# PacketTracerWeb

A scalable, containerized platform for deploying and managing multiple Cisco Packet Tracer instances with web-based remote access, bulk user management, and advanced security controls.

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Cisco Packet Tracer `.deb` file (place in repo root)
- Linux environment (Ubuntu 20.04+)
- Minimum 4GB RAM, 2 CPU cores

### Deploy

```bash
# Full deployment (builds images, starts all services, launches 2 PT containers)
bash deploy-full.sh

# Access at http://localhost
# Default: ptadmin / IlovePT
```

## 📋 Features

- **🐳 Containerized PT Instances** - Multiple Packet Tracer containers running simultaneously
- **👥 Bulk User Management** - Create/delete users in batch via CSV upload
- **🌐 Web-Based Access** - Clientless remote desktop via Apache Guacamole
- **🔒 Security Features** - GeoIP filtering, DNS blocking, access control lists
- **📁 File Sharing** - Persistent `/shared` directory synced across containers
- **⚙️ Management Dashboard** - Create containers, manage users, tune resources, view logs
- **🔄 Health Monitoring** - Real-time container status, resource usage, health checks

## 🏗️ Architecture

```
┌─────────────────────────────────────────┐
│        Nginx (Reverse Proxy)            │
│    GeoIP Filtering & SSL/TLS            │
└──────────┬──────────────────────────────┘
           │
    ┌──────┴──────────┬─────────────┐
    │                 │             │
┌───▼──┐      ┌──────▼─────┐  ┌──▼──────┐
│ PT   │      │ Guacamole   │  │   PT    │
│ VNC1 │      │ + Guacd     │  │ VNC2... │
└──────┘      │ (RDP/VNC)   │  └─────────┘
              └──────┬──────┘
                     │
              ┌──────▼──────┐
              │   MariaDB    │
              │  (Guacamole) │
              └──────────────┘
```

## 📁 Directory Structure

```
├── ptweb-vnc/              # Packet Tracer Docker image
│   ├── Dockerfile          # Container definition
│   ├── customizations/     # Installation scripts
│   └── db-dump.sql         # Guacamole DB schema
├── pt-nginx/               # Nginx config & web UI
│   ├── conf/               # Dynamic nginx configs
│   └── www/                # Static files
├── pt-management/          # Flask management API
│   ├── ptmanagement/       # Application code
│   └── templates/          # Dashboard HTML
├── ssl/                    # SSL/TLS certificates
│   ├── certs/              # SSL certificate files
│   └── keys/               # Private keys
├── shared/                 # Persistent file storage
├── deploy-full.sh          # Main deployment script
├── add-instance.sh         # Add PT container
└── remove-instance.sh      # Remove PT container

```

## 🎮 Management Dashboard

Access at `http://localhost:5000` (after full deploy)

**All operations are handled through the intuitive web interface:**
- Create/delete users and containers
- Bulk user provisioning (CSV import)
- Real-time resource tuning (CPU, Memory)
- Live logs and health checks
- Container lifecycle management
- Nginx configuration management

No command-line tools needed—everything is accessible from the dashboard.

## 🔐 Security

- **GeoIP Filtering** - Restrict access by country (configurable via env vars)
- **DNS Blocking** - Prevent unauthorized Packet Tracer signins via `127.0.0.1` DNS
- **SSL/TLS** - HTTPS enabled by default
- **Access Control** - Role-based permissions (ADMINISTER, READ)
- **Firewall Rules** - Nginx-level request filtering

**Environment Variables:**
```bash
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=FI,SL,UK,US
PRODUCTION_MODE=true
```

## 📊 Database

- **MariaDB** with Guacamole schema
- Users & connections auto-created during bulk operations
- SQL dumps in `ptweb-vnc/db-dump.sql`
- Default credentials: `ptdbuser` / `ptdbpass`

## 🐛 Troubleshooting

**Database connection fails:**
```bash
# Verify pt-management is on pt-stack network
docker inspect pt-management | grep pt-stack

# Restart pt-management with correct network
docker rm pt-management
docker run -d --name pt-management --network pt-stack ...
```

**Files not appearing in `/shared`:**
```bash
# Check mount permissions
docker exec ptvnc1 ls -la /shared

# Verify host path permissions
ls -la shared/
chmod 777 shared/
```

**PT Installation incomplete:**
```bash
# Check container logs
docker logs ptvnc1 | grep pt-install

# Verify /opt/pt exists
docker exec ptvnc1 ls -la /opt/pt/
```


## 🤝 Contributing

- Create feature branches from `dev`
- Test with `bash test-deployment.sh` before committing
- Update documentation for significant changes

## 📝 License

This project includes proprietary Cisco Packet Tracer software. Ensure compliance with Cisco's End User License Agreement (EULA).

## 🎓 Use Cases

- **Educational Institutions** - Provide remote lab access to students
- **Training Programs** - Scale network training across multiple trainees
- **Certification Prep** - Practice environments for CCNA, Network+
- **Network Administration** - Testing configurations in isolated environments

---

**Project Status:** ✅ Production Ready | **Last Updated:** Nov 2025
