# PacketTracerWeb# PacketTracerWeb# PacketTracerWeb



A scalable, containerized platform for deploying and managing multiple Cisco Packet Tracer instances with web-based remote access, bulk user management, and advanced security controls.



## 🚀 Quick StartA scalable, containerized platform for deploying and managing multiple Cisco Packet Tracer instances with web-based remote access, bulk user management, and advanced security controls.A scalable, containerized platform for deploying and managing multiple Cisco Packet Tracer instances with web-based remote access, bulk user management, and advanced security controls.



### Prerequisites

- Docker & Docker Compose

- Cisco Packet Tracer `.deb` file (place in repo root)## 🚀 Quick Start## 🚀 Quick Start

- Linux environment (Ubuntu 20.04+)

- Minimum 4GB RAM, 2 CPU cores



### Deploy### Prerequisites### Prerequisites



```bash- Docker & Docker Compose- Docker & Docker Compose

# Full deployment (builds images, starts all services, launches 2 PT containers)

bash deploy-full.sh- Cisco Packet Tracer `.deb` file (place in repo root)- Cisco Packet Tracer `.deb` file (place in repo root)



# Access at http://localhost- Linux environment (Ubuntu 20.04+)- Linux environment (Ubuntu 20.04+)

# Default: ptadmin / IlovePT

```- Minimum 4GB RAM, 2 CPU cores- Minimum 4GB RAM, 2 CPU cores



## 📋 Features



- **🐳 Containerized PT Instances** - Multiple Packet Tracer AppImage containers running simultaneously### Deploy### Deploy

- **👥 Bulk User Management** - Create/delete users in batch via CSV upload with auto-container provisioning

- **🌐 Web-Based Access** - Clientless remote desktop via Apache Guacamole

- **🔒 Security Features** - GeoIP filtering, DNS blocking, access control lists, HTTPS/SSL

- **📁 File Sharing** - Persistent `/shared` directory synced across containers```bash```

- **⚙️ Management Dashboard** - Create containers, manage users, tune resources, view logs

- **🔄 Health Monitoring** - Real-time container status, resource usage, health checks# Full deployment (builds images, starts all services, launches 2 PT containers)# Full deployment (builds images, starts all services, launches 2 PT containers)

- **🎯 VNC Streaming** - TurboVNC + VirtualGL for hardware-accelerated 3D rendering

bash deploy-full.sh

## 🏗️ Architecture



```

┌──────────────────────────────────────┐# Access at http://localhost

│    Nginx (Port 80/443)               │

│  GeoIP Filtering, SSL/TLS, Routing   │# Default: ptadmin / IlovePT# 

└────────────┬──────────────────────────┘

             │``````

    ┌────────┴────────┬──────────────┐

    │                 │              │

┌───▼───┐      ┌──────▼──────┐  ┌──▼───┐

│PT-Web │      │Guacamole     │  │Other  │## 📋 Features## 📋 Features

│UI/API │      │+ Guacd       │  │Apps   │

└───────┘      │(VNC Proxy)   │  └───────┘

               └──────┬───────┘

                      │- **🐳 Containerized PT Instances** - Multiple Packet Tracer AppImage containers running simultaneously- **🐳 Containerized PT Instances** - Multiple Packet Tracer containers running simultaneously

         ┌────────────┼────────────┐

         │            │            │- **👥 Bulk User Management** - Create/delete users in batch via CSV upload with auto-container provisioning- **👥 Bulk User Management** - Create/delete users in batch via CSV upload

    ┌────▼──┐   ┌────▼──┐   ┌────▼──┐

    │ptvnc1 │   │ptvnc2 │   │ptvnc3 │  (ptnet network)- **🌐 Web-Based Access** - Clientless remote desktop via Apache Guacamole- **🌐 Web-Based Access** - Clientless remote desktop via Apache Guacamole

    │5901   │   │5901   │   │5901   │

    └───────┘   └───────┘   └───────┘- **🔒 Security Features** - GeoIP filtering, DNS blocking, access control lists, HTTPS/SSL- **🔒 Security Features** - GeoIP filtering, DNS blocking, access control lists

         │            │            │

         └────────────┼────────────┘- **📁 File Sharing** - Persistent `/shared` directory synced across containers- **📁 File Sharing** - Persistent `/shared` directory synced across containers

                      │

              ┌───────▼────────┐- **⚙️ Management Dashboard** - Create containers, manage users, tune resources, view logs- **⚙️ Management Dashboard** - Create containers, manage users, tune resources, view logs

              │  MariaDB       │

              │  Guacamole DB  │- **🔄 Health Monitoring** - Real-time container status, resource usage, health checks- **🔄 Health Monitoring** - Real-time container status, resource usage, health checks

              └────────────────┘

```- **🎯 VNC Streaming** - TurboVNC + VirtualGL for hardware-accelerated 3D rendering



## 📁 Directory Structure## 🏗️ Architecture



```## 🏗️ Architecture

├── ptweb-vnc/              # Packet Tracer Docker image

│   ├── Dockerfile          # Container definition (build-time PT install)```

│   ├── customizations/     # Installation scripts (runtime helpers)

│   ├── db-dump.sql         # Guacamole DB schema & initial data```┌─────────────────────────────────────────┐

│   └── pt-nginx/           # Nginx config & web UI

│       ├── conf/           # Dynamic nginx config generation┌──────────────────────────────────────┐│        Nginx (Reverse Proxy)            │

│       ├── generate-nginx-conf.sh  # GeoIP & SSL config generator

│       └── www/            # Static files (downloads, UI)│    Nginx (Port 80/443)               ││    GeoIP Filtering & SSL/TLS            │

├── pt-management/          # Flask management interface (port 5000)

│   ├── ptmanagement/       # Application code│  GeoIP Filtering, SSL/TLS, Routing   │└──────────┬──────────────────────────────┘

│   ├── templates/          # Dashboard HTML

│   └── app.py              # API endpoints└────────────┬──────────────────────────┘           │

├── ssl/                    # SSL/TLS certificates

├── shared/                 # Persistent file storage (mounted to all containers)             │    ┌──────┴──────────┬─────────────┐

├── Scripts/                # Utility scripts (GPU, testing, verification)

├── Documents/              # Implementation documentation & guides    ┌────────┴────────┬──────────────┐    │                 │             │

│

├── deploy-full.sh          # Full stack deployment (main script)    │                 │              │┌───▼──┐      ┌──────▼─────┐  ┌──▼──────┐

├── deploy.sh               # Fast deployment (no management interface)

├── add-instance.sh         # Add PT containers at runtime (uses ptnet)┌───▼───┐      ┌──────▼──────┐  ┌──▼───┐│ PT   │      │ Guacamole   │  │   PT    │

├── remove-instance.sh      # Remove PT containers

├── generate-dynamic-connections.sh  # Auto-generate Guacamole connections│PT-Web │      │Guacamole     │  │Other  ││ VNC1 │      │ + Guacd     │  │ VNC2... │

├── generate-ssl-cert.sh    # Generate self-signed SSL certificates

├── health_check.sh         # Deployment verification│UI/API │      │+ Guacd       │  │Apps   │└──────┘      │ (RDP/VNC)   │  └─────────┘

└── tune_ptvnc.sh           # Adjust container resources (CPU/Memory)

```└───────┘      │(VNC Proxy)   │  └───────┘              └──────┬──────┘



## 🎮 Management Dashboard               └──────┬───────┘                     │



Access at `http://localhost:5000` (after full deploy)                      │              ┌──────▼──────┐



**All operations are handled through the intuitive web interface:**         ┌────────────┼────────────┐              │   MariaDB    │

- Create/delete users and containers (auto-provisioned on ptnet)

- Bulk user provisioning (CSV import with VNC auto-connection)         │            │            │              │  (Guacamole) │

- Real-time resource tuning (CPU, Memory, ulimits)

- Live container logs and health checks    ┌────▼──┐   ┌────▼──┐   ┌────▼──┐              └──────────────┘

- Container lifecycle management

- Nginx configuration management    │ptvnc1 │   │ptvnc2 │   │ptvnc3 │  (ptnet network)```



No command-line tools needed—everything is accessible from the dashboard.    │TurboVNC



## 🔌 Deployment Modes    │5901   │   │5901   │   │5901   │## 📁 Directory Structure



### Fast Deploy (Desktop/Development)    └───────┘   └───────┘   └───────┘

```bash

bash deploy.sh         │            │            │```

# Starts 2 PT containers + Guacamole stack

# No management interface         └────────────┼────────────┘├── ptweb-vnc/              # Packet Tracer Docker image

# Faster boot time

```                      ││   ├── Dockerfile          # Container definition



### Full Deploy (Production/Lab)              ┌───────▼────────┐│   ├── customizations/     # Installation scripts

```bash

bash deploy-full.sh              │  MariaDB       ││   └── db-dump.sql         # Guacamole DB schema

# Starts 2 PT containers + Full management interface

# Includes Flask API for bulk user management              │  Guacamole DB  │├── pt-nginx/               # Nginx config & web UI

# Recommended for labs with 20+ students

```              │  (ptnet)       ││   ├── conf/               # Dynamic nginx configs



### Add/Remove Instances              └────────────────┘│   └── www/                # Static files

```bash

# Add 3 new containers at runtime```├── pt-management/          # Flask management API

bash add-instance.sh 3

│   ├── ptmanagement/       # Application code

# Remove by number or name

bash remove-instance.sh 5          # Remove ptvnc5## 📁 Directory Structure│   └── templates/          # Dashboard HTML

bash remove-instance.sh ptvnc7     # Remove by name

bash remove-instance.sh 7 8 9      # Remove multiple├── ssl/                    # SSL/TLS certificates

```

```│   ├── certs/              # SSL certificate files

## 🔐 Security & Network

├── ptweb-vnc/              # Packet Tracer Docker image│   └── keys/               # Private keys

### Network Architecture

- **ptnet**: Bridge network connecting all Guacamole services & ptvnc containers│   ├── Dockerfile          # Container definition (build-time PT install)├── shared/                 # Persistent file storage

- Containers join ptnet at startup (via `--network ptnet` flag)

- DNS resolution: `ptvnc1`, `ptvnc2`, etc. resolve automatically on ptnet│   ├── customizations/     # Installation scripts (runtime helpers)├── deploy-full.sh          # Main deployment script

- Guacamole connection proxy: `pt-guacd` (4822) and `pt-guacamole` (8080)

│   ├── db-dump.sql         # Guacamole DB schema & initial data├── add-instance.sh         # Add PT container

### Security Features

- **GeoIP Filtering** - Restrict access by country (configurable via env vars)│   └── pt-nginx/           # Nginx config & web UI└── remove-instance.sh      # Remove PT container

- **DNS Blocking** - Prevent unauthorized signins

- **SSL/TLS** - HTTPS enabled by default│       ├── conf/           # Dynamic nginx config generation

- **Access Control** - Role-based permissions (ADMINISTER, READ)

- **Firewall Rules** - Nginx-level request filtering│       ├── generate-nginx-conf.sh  # GeoIP & SSL config generator```



**Environment Variables (in `.env`):**│       └── www/            # Static files (downloads, UI)

```bash

NGINX_GEOIP_ALLOW=true├── pt-management/          # Flask management interface (port 5000)## 🎮 Management Dashboard

GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,FI

PRODUCTION_MODE=true│   ├── ptmanagement/       # Application code

ENABLE_HTTPS=true

```│   ├── templates/          # Dashboard HTMLAccess at `http://localhost:5000` (after full deploy)



## 🗄️ Database│   └── app.py              # API endpoints



- **MariaDB** with Guacamole 1.6.0 schema├── ssl/                    # SSL/TLS certificates**All operations are handled through the intuitive web interface:**

- Users & connections auto-created during bulk operations

- Connection mapping:├── shared/                 # Persistent file storage (mounted to all containers)- Create/delete users and containers

  - Guacamole name: `pt01`, `pt02`, etc. (display in UI)

  - Container hostname: `ptvnc1`, `ptvnc2`, etc. (DNS resolution on ptnet)├── Scripts/                # Utility scripts (GPU, testing, verification)- Bulk user provisioning (CSV import)

  - Proxy: `pt-guacd:4822` (all connections use same proxy)

├── Documents/              # Implementation documentation & guides- Real-time resource tuning (CPU, Memory)

**Default Credentials:**

- Database: `ptdbuser` / `ptdbpass`│- Live logs and health checks

- Guacamole: `ptadmin` / `IlovePT`

├── deploy-full.sh          # Full stack deployment (main script)- Container lifecycle management

## 🐛 Troubleshooting

├── deploy.sh               # Fast deployment (no management interface)- Nginx configuration management

### Guacamole Can't Connect to VNC

```bash├── add-instance.sh         # Add PT containers at runtime (uses ptnet)

# Check guacd is on ptnet network

docker inspect pt-guacd | grep -A 5 '"ptnet"'├── remove-instance.sh      # Remove PT containersNo command-line tools needed—everything is accessible from the dashboard.



# Verify proxy_hostname in database (must be 'pt-guacd', not 'guacd')├── generate-dynamic-connections.sh  # Auto-generate Guacamole connections

docker exec guacamole-mariadb mariadb -u ptdbuser -p'ptdbpass' guacamole_db \

  -e "SELECT connection_name, proxy_hostname FROM guacamole_connection LIMIT 5;"├── generate-ssl-cert.sh    # Generate self-signed SSL certificates## 🔐 Security



# Test DNS resolution├── health_check.sh         # Deployment verification

docker run --rm --network ptnet busybox ping -c 1 ptvnc1

docker run --rm --network ptnet busybox ping -c 1 pt-guacd└── tune_ptvnc.sh           # Adjust container resources (CPU/Memory)- **GeoIP Filtering** - Restrict access by country (configurable via env vars)

```

- **DNS Blocking** - Prevent unauthorized Packet Tracer signins via `127.0.0.1` DNS

### Files Not Appearing in `/shared`

```bash```- **SSL/TLS** - HTTPS enabled by default

# Check mount is present

docker exec ptvnc1 mount | grep shared- **Access Control** - Role-based permissions (ADMINISTER, READ)



# Verify host path permissions## 🎮 Management Dashboard- **Firewall Rules** - Nginx-level request filtering

ls -la shared/

chmod 777 shared/



# Fix container side permissionsAccess at `http://localhost:5000` (after full deploy)**Environment Variables:**

docker exec ptvnc1 chmod 777 /shared

``````bash



### PT Installation Incomplete**All operations are handled through the intuitive web interface:**NGINX_GEOIP_ALLOW=true

```bash

# Check docker build logs- Create/delete users and containers (auto-provisioned on ptnet)GEOIP_ALLOW_COUNTRIES=FI,SL,UK,US

docker build -t ptvnc ptweb-vnc/ 2>&1 | grep -i "pt-install\|error"

- Bulk user provisioning (CSV import with VNC auto-connection)PRODUCTION_MODE=true

# Verify binary exists

docker exec ptvnc1 ls -lh /opt/pt/packettracer.AppImage- Real-time resource tuning (CPU, Memory, ulimits)```



# Check AppImage extraction (for VNC launch)- Live container logs and health checks

docker exec ptvnc1 ls -la /tmp/squashfs-root/ || echo "Not extracted yet"

```- Container lifecycle management## 📊 Database



### Container Won't Start or Exit Immediately- Nginx configuration management

```bash

# Check container logs- **MariaDB** with Guacamole schema

docker logs ptvnc1 | tail -50

No command-line tools needed—everything is accessible from the dashboard.- Users & connections auto-created during bulk operations

# Verify ptnet network exists

docker network ls | grep ptnet- SQL dumps in `ptweb-vnc/db-dump.sql`



# Check if container properly joined network## 🔌 Deployment Modes- Default credentials: `ptdbuser` / `ptdbpass`

docker inspect ptvnc1 | grep -A 10 '"Networks"'

```



## 📋 Bulk User Management Workflow### Fast Deploy (Desktop/Development)## 🐛 Troubleshooting



### Create Users via Dashboard```bash

1. Navigate to http://localhost:5000

2. Login with `ptadmin` / `IlovePT`bash deploy.sh**Database connection fails:**

3. Upload CSV with columns: `username,password,create_container,is_admin`

4. System auto-creates:# Starts 2 PT containers + Guacamole stack```bash

   - Guacamole users

   - Docker containers on ptnet (if create_container=true)# No management interface# Verify pt-management is on pt-stack network

   - VNC connections (pt01, pt02, etc.)

   - Database entries with correct proxy_hostname# Faster boot timedocker inspect pt-management | grep pt-stack



### CSV Format```

```csv

username,password,create_container,is_admin# Restart pt-management with correct network

student1,password123,true,false

student2,password123,true,false### Full Deploy (Production/Lab)docker rm pt-management

instructor1,password123,false,true

``````bashdocker run -d --name pt-management --network pt-stack ...



### Resultbash deploy-full.sh```

- Each user gets assigned container (ptvnc5, ptvnc6, etc.)

- Guacamole connection auto-created (pt05, pt06, etc.)# Starts 2 PT containers + Full management interface

- Connection proxy: `pt-guacd:4822`

- Container hostname resolves via DNS on ptnet# Includes Flask API for bulk user management**Files not appearing in `/shared`:**



## 📊 Important Recent Fixes# Recommended for labs with 20+ students```bash



### ✅ Network Configuration (Nov 2025)```# Check mount permissions

- Containers now join ptnet **at startup** (not post-connection)

- Fixed DNS resolution issuesdocker exec ptvnc1 ls -la /shared

- All services on same network for reliable communication

### Add/Remove Instances

### ✅ Bulk User Creation (Nov 2025)

- Fixed container network to use `ptnet` (was `pt-stack`)```bash# Verify host path permissions

- Corrected database proxy_hostname to `pt-guacd` (was hardcoded `guacd`)

- Management interface now creates correct connections# Add 3 new containers at runtimels -la shared/



### ✅ Guacamole Configuration (Nov 2025)bash add-instance.sh 3chmod 777 shared/

- Environment: `GUACAMOLE_GUACD_HOSTNAME=pt-guacd`

- Database: All connections now have `proxy_hostname='pt-guacd'````

- Verified DNS resolution and VNC connectivity

# Remove by number or name

## 🤝 Contributing

bash remove-instance.sh 5          # Remove ptvnc5**PT Installation incomplete:**

- Create feature branches from `dev`

- Test with `bash test-deployment.sh` before committingbash remove-instance.sh ptvnc7     # Remove by name```bash

- Update documentation for significant changes

- Move utility scripts to `Scripts/` folderbash remove-instance.sh 7 8 9      # Remove multiple# Check container logs

- Archive old docs in `Documents/` folder

```docker logs ptvnc1 | grep pt-install

## 📝 License



This project includes proprietary Cisco Packet Tracer software. Ensure compliance with Cisco's End User License Agreement (EULA).

## 🔐 Security & Network# Verify /opt/pt exists

## 🎓 Use Cases

docker exec ptvnc1 ls -la /opt/pt/

- **Educational Institutions** - Provide remote lab access to 40+ students

- **Training Programs** - Scale network training across multiple trainees### Network Architecture```

- **Certification Prep** - Practice environments for CCNA, Network+

- **Network Administration** - Testing configurations in isolated environments- **ptnet**: Bridge network connecting all Guacamole services & ptvnc containers

- **Bulk Testing** - Rapidly spin up/down test containers

- Containers join ptnet at startup (via `--network ptnet` flag)

---

- DNS resolution: `ptvnc1`, `ptvnc2`, etc. resolve automatically on ptnet## 🤝 Contributing

**Project Status:** ✅ Production Ready | **Last Updated:** Nov 21, 2025  

**Version:** 3.0 (Network Architecture & Bulk User Management)  - Guacamole connection proxy: `pt-guacd` (4822) and `pt-guacamole` (8080)

**Supported:** Ubuntu 20.04+ | Docker 20.10+ | Guacamole 1.6.0+

- Create feature branches from `dev`

### Security Features- Test with `bash test-deployment.sh` before committing

- **GeoIP Filtering** - Restrict access by country (configurable via env vars)- Update documentation for significant changes

- **DNS Blocking** - Prevent unauthorized signins

- **SSL/TLS** - HTTPS enabled by default## 📝 License

- **Access Control** - Role-based permissions (ADMINISTER, READ)

- **Firewall Rules** - Nginx-level request filteringThis project includes proprietary Cisco Packet Tracer software. Ensure compliance with Cisco's End User License Agreement (EULA).



**Environment Variables (in `.env`):**## 🎓 Use Cases

```bash

NGINX_GEOIP_ALLOW=true- **Educational Institutions** - Provide remote lab access to students

GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,FI- **Training Programs** - Scale network training across multiple trainees

PRODUCTION_MODE=true- **Certification Prep** - Practice environments for CCNA, Network+

ENABLE_HTTPS=true- **Network Administration** - Testing configurations in isolated environments

```

---

## 🗄️ Database

**Project Status:** ✅ Production Ready | **Last Updated:** Nov 2025

- **MariaDB** with Guacamole 1.6.0 schema
- Users & connections auto-created during bulk operations
- Connection mapping:
  - Guacamole name: `pt01`, `pt02`, etc. (display in UI)
  - Container hostname: `ptvnc1`, `ptvnc2`, etc. (DNS resolution on ptnet)
  - Proxy: `pt-guacd:4822` (all connections use same proxy)

**Default Credentials:**
- Database: `ptdbuser` / `ptdbpass`
- Guacamole: `ptadmin` / `IlovePT`

## 🐛 Troubleshooting

### Guacamole Can't Connect to VNC
```bash
# Check guacd is on ptnet network
docker inspect pt-guacd | grep -A 5 '"ptnet"'

# Verify proxy_hostname in database (must be 'pt-guacd', not 'guacd')
docker exec guacamole-mariadb mariadb -u ptdbuser -p'ptdbpass' guacamole_db \
  -e "SELECT connection_name, proxy_hostname FROM guacamole_connection LIMIT 5;"

# Test DNS resolution
docker run --rm --network ptnet busybox ping -c 1 ptvnc1
docker run --rm --network ptnet busybox ping -c 1 pt-guacd
```

### Files Not Appearing in `/shared`
```bash
# Check mount is present
docker exec ptvnc1 mount | grep shared

# Verify host path permissions
ls -la shared/
chmod 777 shared/

# Fix container side permissions
docker exec ptvnc1 chmod 777 /shared
```

### PT Installation Incomplete
```bash
# Check docker build logs
docker build -t ptvnc ptweb-vnc/ 2>&1 | grep -i "pt-install\|error"

# Verify binary exists
docker exec ptvnc1 ls -lh /opt/pt/packettracer.AppImage

# Check AppImage extraction (for VNC launch)
docker exec ptvnc1 ls -la /tmp/squashfs-root/ || echo "Not extracted yet"
```

### Container Won't Start or Exit Immediately
```bash
# Check container logs
docker logs ptvnc1 | tail -50

# Verify ptnet network exists
docker network ls | grep ptnet

# Check if container properly joined network
docker inspect ptvnc1 | grep -A 10 '"Networks"'
```

## 📋 Bulk User Management Workflow

### Create Users via Dashboard
1. Navigate to http://localhost:5000
2. Login with `ptadmin` / `IlovePT`
3. Upload CSV with columns: `username,password,create_container,is_admin`
4. System auto-creates:
   - Guacamole users
   - Docker containers on ptnet (if create_container=true)
   - VNC connections (pt01, pt02, etc.)
   - Database entries with correct proxy_hostname

### CSV Format
```csv
username,password,create_container,is_admin
student1,password123,true,false
student2,password123,true,false
instructor1,password123,false,true
```

### Result
- Each user gets assigned container (ptvnc5, ptvnc6, etc.)
- Guacamole connection auto-created (pt05, pt06, etc.)
- Connection proxy: `pt-guacd:4822`
- Container hostname resolves via DNS on ptnet

## 📊 Important Recent Fixes

### ✅ Network Configuration (Nov 2025)
- Containers now join ptnet **at startup** (not post-connection)
- Fixed DNS resolution issues
- All services on same network for reliable communication

### ✅ Bulk User Creation (Nov 2025)
- Fixed container network to use `ptnet` (was `pt-stack`)
- Corrected database proxy_hostname to `pt-guacd` (was hardcoded `guacd`)
- Management interface now creates correct connections

### ✅ Guacamole Configuration (Nov 2025)
- Environment: `GUACAMOLE_GUACD_HOSTNAME=pt-guacd`
- Database: All connections now have `proxy_hostname='pt-guacd'`
- Verified DNS resolution and VNC connectivity

## 🤝 Contributing

- Create feature branches from `dev`
- Test with `bash health_check.sh` before committing
- Update documentation for significant changes
- Move utility scripts to `Scripts/` folder
- Archive old docs in `Documents/` folder

## 📝 License

This project includes proprietary Cisco Packet Tracer software. Ensure compliance with Cisco's End User License Agreement (EULA).

## 🎓 Use Cases

- **Educational Institutions** - Provide remote lab access to 40+ students
- **Training Programs** - Scale network training across multiple trainees
- **Certification Prep** - Practice environments for CCNA, Network+
- **Network Administration** - Testing configurations in isolated environments
- **Bulk Testing** - Rapidly spin up/down test containers

---

**Project Status:** ✅ Production Ready | **Last Updated:** Nov 21, 2025  
**Version:** 2.0 (Network & Bulk User Fixes)  
**Supported:** Ubuntu 20.04+ | Docker 20.10+ | Guacamole 1.6.0+
