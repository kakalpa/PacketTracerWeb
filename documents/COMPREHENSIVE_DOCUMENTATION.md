# PacketTracerWeb: Comprehensive System Documentation

## Table of Contents

1. Executive Summary
2. System Architecture
3. Theoretical Foundation
4. Technical Implementation
5. Installation Guide
6. Configuration Management
7. Security Features
8. Deployment Procedures
9. Operations and Maintenance
10. Troubleshooting Guide
11. Appendices

---

## 1. Executive Summary

### 1.1 Project Overview

PacketTracerWeb is a containerized, web-based deployment solution for Cisco Packet Tracer, enabling multiple instances of the networking simulation application to run simultaneously within Docker containers and be accessed through a unified web interface. The system combines Docker containerization, Nginx web server, Apache Guacamole remote access, and MariaDB database technologies to create a scalable, secure, and manageable platform.

### 1.2 Key Objectives

- Provide remote, browser-based access to Cisco Packet Tracer instances
- Support multiple concurrent users across isolated instances
- Enable dynamic scaling (add/remove instances at runtime)
- Implement geographic-based access control via GeoIP filtering
- Provide optional HTTPS/TLS encryption for secure connections
- Maintain high availability and minimal downtime during operations
- Offer comprehensive health monitoring and testing capabilities

### 1.3 Target Use Cases

- Educational institutions managing Packet Tracer labs
- Corporate training environments
- Remote technical assessment platforms
- Distributed networking training scenarios
- Cloud-based networking education platforms

### 1.4 System Capabilities

- Multi-instance support (2, 4, 8, or more concurrent instances)
- Browser-based remote desktop access via Guacamole
- Dynamic instance scaling without service interruption
- GeoIP-based access control (allowlist and blocklist modes)
- Optional HTTPS/TLS with automatic HTTP-to-HTTPS redirection
- File sharing through mounted network volumes
- Automated database connection management
- Comprehensive health monitoring (57-test validation suite)
- Resource tuning capabilities

---

## 2. System Architecture

### 2.1 High-Level Architecture Overview

The PacketTracerWeb system consists of five primary component layers:

```
    +--------------------- Internet ----------------------+
    |                                                       |
    +---- Load Balancer / Reverse Proxy (Optional) --------+
    |                                                       |
    +------ Nginx Reverse Proxy (pt-nginx1) ------+        |
    |  - SSL/TLS Termination (if HTTPS enabled)   |        |
    |  - GeoIP Filtering & Access Control         |        |
    |  - Static Content Serving                   |        |
    |  - WebSocket Tunneling to Guacamole         |        |
    |                                             |        |
    +------ Guacamole Services ------+            |        |
    |                                |            |        |
    | - pt-guacamole (Tomcat)       |            |        |
    |   * User authentication        |            |        |
    |   * Connection proxying        |            |        |
    |   * Session management         |            |        |
    |                                |            |        |
    | - pt-guacd (Daemon)            |            |        |
    |   * Remote protocol handling    |            |        |
    |   * VNC connection management   |            |        |
    |                                |            |        |
    +------ MariaDB Database ------+ |            |        |
    |                              | |            |        |
    | - guacamole_db               | |            |        |
    |   * User accounts            | |            |        |
    |   * Connection definitions    | |            |        |
    |   * Session logs             | |            |        |
    |                              | |            |        |
    +------ Docker Network ------+-+-+            |        |
    |                                             |        |
    | +-- ptvnc1 ---+ +-- ptvnc2 ---+           |        |
    | |             | |             |           |        |
    | | Ubuntu 22.04| | Ubuntu 22.04|  ... more |        |
    | | XFCE Desktop| | XFCE Desktop|  instances|        |
    | | VNC Server  | | VNC Server  |           |        |
    | | Packet      | | Packet      |           |        |
    | | Tracer      | | Tracer      |           |        |
    | |             | |             |           |        |
    | +-- /shared --+ +-- /shared --+           |        |
    |   (bind-mounted to host)                   |        |
    |                                            |        |
    +--------------------------------------------+        |
```

### 2.2 Container Components

#### 2.2.1 Packet Tracer Containers (ptvnc1, ptvnc2, ...)

**Purpose**: Execute Cisco Packet Tracer instances with GUI environment

**Base Image**: Ubuntu 22.04

**Key Components**:
- XFCE desktop environment for graphical interface
- TightVNC server for remote desktop access
- Cisco Packet Tracer application installation
- Shared volume mount at /shared for file exchange
- Resource isolation via CPU and memory limits

**Resource Allocation**:
- CPU: 0.1 cores (configurable via tune_ptvnc.sh)
- Memory: 1GB (configurable via tune_ptvnc.sh)
- Storage: Persistent volume (pt_opt)

#### 2.2.2 Nginx Container (pt-nginx1)

**Purpose**: Reverse proxy and security layer

**Base Image**: Alpine Linux with compiled GeoIP module

**Key Features**:
- HTTP/1.1, HTTP/2, and HTTPS/TLS support
- GeoIP country detection and filtering
- SSL/TLS certificate termination
- WebSocket support for Guacamole
- Static file serving (downloads directory)
- Automatic HTTP-to-HTTPS redirection (when enabled)

**Key Modules**:
- ngx_http_geoip_module (for geographic filtering)
- ngx_http_ssl_module (for HTTPS)
- ngx_http_v2_module (for HTTP/2)

#### 2.2.3 Guacamole Application (pt-guacamole)

**Purpose**: Remote access gateway and connection management

**Base Image**: Official Guacamole image (Tomcat-based)

**Key Responsibilities**:
- User authentication and session management
- Connection proxying to VNC servers
- WebSocket tunnel management
- User interface rendering

#### 2.2.4 Guacamole Daemon (pt-guacd)

**Purpose**: Protocol handler and remote desktop proxy

**Responsibilities**:
- VNC protocol translation
- WebSocket-to-VNC bridging
- Connection state management
- Performance optimization for remote protocols

#### 2.2.5 MariaDB Database (guacamole-mariadb)

**Purpose**: Persistent data storage for Guacamole

**Database Schema**:
- Users and authentication credentials
- Connection definitions (host, port, protocol)
- User permissions and connection access
- Session logs and audit trails
- Custom attributes and metadata

**Volume**: dbdump (persistent storage)

### 2.3 Data Flow Diagram

```
User Browser
    |
    | HTTP/HTTPS
    v
+-------------------+
| Nginx Reverse Proxy|
| - GeoIP Filtering  |
| - SSL/TLS         |
| - WebSocket Proxy |
+-------------------+
    |
    | WebSocket
    v
+-------------------+
| Guacamole Service |
| - Authentication  |
| - Session Mgmt    |
+-------------------+
    |
    | VNC Protocol
    v
+-------------------+
| Guacamole Daemon  |
| - Protocol Handler|
+-------------------+
    |
    | VNC over TCP
    v
+-------------------+
| Packet Tracer VNC |
| Servers           |
| (ptvnc1, ptvnc2..)
+-------------------+
    |
    | Shared Volume
    v
+-------------------+
| Host File System  |
| /shared           |
+-------------------+
```

### 2.4 Network Architecture

#### 2.4.1 Docker Network Configuration

- Network Driver: bridge
- Network Name: bridge (default Docker network)
- Subnet: 172.17.0.0/16 (default)
- Gateway: 172.17.0.1
- DNS: Docker daemon (127.0.0.11:53)

#### 2.4.2 Port Mapping

| Service | Container Port | Host Port | Protocol |
|---------|---------------|-----------|----------|
| Nginx HTTP | 80 | 80 | HTTP |
| Nginx HTTPS | 443 | 443 | HTTPS (if enabled) |
| Guacamole | 8080 | Not exposed | HTTP (internal only) |
| Guacamole Daemon | 4822 | Not exposed | TCP (internal only) |
| MariaDB | 3306 | Not exposed | TCP (internal only) |
| VNC Servers | 5900+ | Not exposed | TCP (internal only) |

#### 2.4.3 Service Discovery

- Container linking ensures service discovery
- DNS resolution via Docker daemon
- Environment variables for connection strings
- Guacamole database stores connection parameters

### 2.5 Storage Architecture

#### 2.5.1 Volume Types

**Named Volumes**:
- pt_opt: Persistent Packet Tracer installation directory
- dbdump: MariaDB data and schemas

**Bind Mounts**:
- ./shared: Shared file exchange directory
- ./ptweb-vnc/pt-nginx/conf: Nginx configuration
- ./ptweb-vnc/pt-nginx/www: Static web content
- ./ssl: SSL certificates (when HTTPS enabled)

#### 2.5.2 Data Persistence

- Application data: pt_opt volume (survives container restart)
- Database data: dbdump volume (persistent across deployments)
- User files: /shared bind mount (accessible from host)
- Configuration: Config files in repository directory

---

## 3. Theoretical Foundation

### 3.1 Containerization Technology (Docker)

#### 3.1.1 Principle of Container Isolation

Docker containers provide operating system-level virtualization through:

- Namespace isolation: Each container has isolated view of processes, network, filesystem
- Control groups (cgroups): Resource limitation at kernel level
- Union filesystem: Layered filesystem with copy-on-write semantics

**Benefits for PacketTracerWeb**:
- Each Packet Tracer instance runs in isolated environment
- Resource limits prevent one instance from consuming all system resources
- Lightweight compared to virtual machines (shares kernel)
- Fast startup times (seconds vs minutes for VMs)

#### 3.1.2 Multi-stage Build Process

The Dockerfile implements:
1. Base image with runtime dependencies
2. User creation and permission setup
3. VNC server configuration
4. Application entrypoint definition

**Optimization Strategy**:
- Minimal base image (Ubuntu 22.04)
- Single RUN command to minimize layers
- apt-get cleanup to reduce image size
- Only runtime dependencies (no build tools)

### 3.2 Reverse Proxy Theory (Nginx)

#### 3.2.1 Purpose and Benefits

Nginx serves as the single entry point for all client requests:

1. **Connection Consolidation**: Single public-facing endpoint
2. **Protocol Handling**: Manages TLS/SSL termination
3. **Load Distribution**: Routes traffic to appropriate backends
4. **Security Layer**: Filters requests based on geographic origin
5. **Static Content**: Serves files without backend involvement
6. **Protocol Translation**: Bridges HTTP/WebSocket to VNC

#### 3.2.2 GeoIP Filtering Implementation

GeoIP filtering operates at the IP layer within Nginx:

```
Client IP
    |
    v
Nginx GeoIP Module
    |
    +-- Lookup in GeoIP Database
    |   (binary search in country codes)
    |
    v
Extract Country Code
    |
    v
Map to Allow/Block List
    |
    +-- If in allow list: ACCEPT
    +-- If in block list: DROP
    +-- If in neither: ACCEPT (by default)
    |
    v
Route to Guacamole Proxy
```

**Algorithm Efficiency**:
- GeoIP lookup: O(log n) binary search
- Database indexed by IP address ranges
- Cached in memory after first load

### 3.3 Remote Desktop Protocol (VNC)

#### 3.3.1 VNC Architecture

VNC (Virtual Network Computing) operates using:

1. **Client-Server Model**: Separate control and display channels
2. **Framebuffer Sharing**: Server sends screen updates to client
3. **Input Events**: Client sends keyboard and mouse events
4. **Efficient Updates**: Only changed regions transmitted

#### 3.3.2 TightVNC Optimization

TightVNC improves on standard VNC:
- Compression algorithms reduce bandwidth
- Color encoding optimization
- Efficient region detection
- Improved performance on limited bandwidth

### 3.4 Web-Based Remote Access (Guacamole)

#### 3.4.1 Guacamole Protocol

Guacamole implements its own protocol:

- Clientless: Pure HTML5/JavaScript client
- Protocol-agnostic: Supports VNC, RDP, SSH, Telnet
- Tunneling: Works through HTTP/WebSocket
- Stateless: Sessions survive client reconnection

#### 3.4.2 WebSocket Bridging

```
Browser (HTML5)
    |
    | WebSocket over HTTPS
    |
Guacamole Server
    |
    +-- Decode Guacamole Protocol
    |
    v
VNC Connection
    |
    | Standard VNC over TCP
    |
Packet Tracer VNC Server
```

**Advantages**:
- Only needs HTTP(S) port open
- Works through firewalls
- Can be proxied through load balancers
- Native browser support (no Java applet)

### 3.5 Database Design (Relational Model)

#### 3.5.1 Schema Design Principles

Guacamole database follows normalization principles:

1. **First Normal Form (1NF)**: Atomic attributes
2. **Second Normal Form (2NF)**: Partial dependency removed
3. **Third Normal Form (3NF)**: Transitive dependency removed

#### 3.5.2 Key Entities

- guacamole_user: User accounts and authentication
- guacamole_connection: Connection definitions
- guacamole_connection_parameter: Per-connection settings
- guacamole_user_connection: User-to-connection mappings

---

## 4. Technical Implementation Details

### 4.1 Deployment Script Architecture

#### 4.1.1 Deploy.sh Workflow

The main deployment script (deploy.sh) follows this sequence:

```
1. Environment Setup
   - Load .env configuration
   - Set variables from environment or defaults
   - Verify Packet Tracer .deb file exists

2. Image Building
   - Build ptvnc image (if not exists)
   - Build pt-nginx image (if not exists)
   - Tag images appropriately

3. Infrastructure Services
   - Start MariaDB container
   - Wait for database readiness
   - Import Guacamole schema

4. Backend Services
   - Start Guacamole Daemon (guacd)
   - Start Guacamole Application
   - Wait for service availability

5. Packet Tracer Instances
   - Create /shared directory structure
   - Start ptvnc containers (count from numofPT variable)
   - Wait for Packet Tracer installation
   - Create desktop symlinks

6. Web Layer
   - Generate ptweb.conf from template
   - Substitute Guacamole IP address
   - Handle HTTPS configuration (if enabled)
   - Mount SSL certificates (if HTTPS enabled)
   - Start Nginx container

7. Database Population
   - Generate dynamic connections
   - Create Guacamole connection entries
   - Associate users to connections

8. Validation
   - Wait for all services to be healthy
   - Verify Packet Tracer binary presence
   - Check container logs for errors
   - Report deployment status
```

#### 4.1.2 Configuration Generation

The system generates nginx configuration at runtime:

```bash
generate_nginx_config() {
    # HTTP server block (always included)
    # Conditional HTTPS redirect if ENABLE_HTTPS=true
    # Conditional HTTPS server block if ENABLE_HTTPS=true
    # Common location blocks for /downloads/, /files, /
}
```

This dynamic generation ensures:
- Configuration matches deployment mode
- Guacamole IP is correctly substituted
- SSL certificates are properly referenced
- No hardcoded IP addresses in repository

### 4.2 GeoIP Implementation

#### 4.2.1 Database Format

GeoIP.dat is a binary database with:

- IP range to country code mapping
- Optimized for fast lookup
- Indexed structures for binary search
- Compact storage format

#### 4.2.2 Nginx GeoIP Module Integration

The ngx_http_geoip_module provides:

```nginx
geoip_country /usr/share/GeoIP/GeoIP.dat;

map $geoip_country_code $allowed_country {
    default 0;
    "US" 1;
    "CA" 1;
    "GB" 1;
}

map $geoip_country_code $blocked_country {
    default 0;
    "CN" 1;
    "RU" 1;
}
```

#### 4.2.3 Request Filtering Logic

```
Incoming Request
    |
    v
Extract Source IP
    |
    v
Lookup in GeoIP Database
    |
    v
Get Country Code
    |
    +-- Check Against Allow List
    |   (if NGINX_GEOIP_ALLOW=true)
    |   - If country not in list: RETURN 444 (close connection)
    |
    +-- Check Against Block List
    |   (if NGINX_GEOIP_BLOCK=true)
    |   - If country in list: RETURN 444 (close connection)
    |
    v
Allow Request to Proceed
    |
    v
Proxy to Guacamole Backend
```

### 4.3 HTTPS/TLS Implementation

#### 4.3.1 Certificate Architecture

```
Certificate Generation (openssl)
    |
    +-- Private Key: RSA 2048-bit
    +-- Certificate: X.509 format
    +-- Subject: CN=localhost
    +-- Validity: 365 days
    |
    v
Host Storage
    |
    +-- ./ssl/server.crt (certificate)
    +-- ./ssl/server.key (private key)
    |
    v
Container Mounting
    |
    +-- Mount to /etc/ssl/certs/server.crt
    +-- Mount to /etc/ssl/private/server.key
    |
    v
Nginx Configuration
    |
    +-- ssl_certificate directive
    +-- ssl_certificate_key directive
    +-- ssl_protocols: TLSv1.2, TLSv1.3
    +-- ssl_ciphers: HIGH:!aNULL:!MD5
```

#### 4.3.2 HTTPS Redirect Mechanism

When ENABLE_HTTPS=true:

```nginx
server {
    listen 80;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/server.crt;
    ssl_certificate_key /etc/ssl/private/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
}
```

**Flow**:
1. Client connects to HTTP (port 80)
2. Nginx returns 301 Moved Permanently
3. Client redirects to HTTPS (port 443)
4. TLS handshake occurs
5. Encrypted communication established

### 4.4 Dynamic Connection Management

#### 4.4.1 Connection Generation Process

The generate-dynamic-connections.sh script:

1. Queries Docker for running ptvnc containers
2. Extracts instance numbers from container names
3. Constructs VNC connection strings
4. Inserts into guacamole_connection table
5. Associates with guacamole_user accounts

#### 4.4.2 SQL Generation

```sql
INSERT INTO guacamole_connection (connection_name, protocol, max_connections)
VALUES ('pt01', 'vnc', 1);

INSERT INTO guacamole_connection_parameter (connection_id, parameter_name, parameter_value)
VALUES (LAST_INSERT_ID(), 'hostname', 'ptvnc1');
VALUES (LAST_INSERT_ID(), 'port', '5900');
VALUES (LAST_INSERT_ID(), 'read-only', 'true');
```

---

## 5. Installation Guide

### 5.1 Prerequisites

#### 5.1.1 System Requirements

- Operating System: Linux (Ubuntu 20.04 LTS or newer recommended)
- Kernel: Linux 4.0+ (for Docker support)
- RAM: Minimum 8GB (4GB per 2 instances recommended)
- CPU: Minimum 4 cores (2 per instance recommended)
- Storage: 50GB free space (for images and volumes)
- Docker: Version 20.10 or newer
- Docker Compose: Version 1.29 or newer (optional)

#### 5.1.2 Software Dependencies

- Git (for repository cloning)
- Docker CLI (for container management)
- wget or curl (for GeoIP database download)
- openssl (for certificate generation)
- bash (for script execution)

#### 5.1.3 Cisco Packet Tracer

- Version: 9.0 or newer
- File Format: .deb (Debian package)
- Architecture: 64-bit (amd64)
- License: Valid Cisco EULA acceptance required

### 5.2 Step-by-Step Installation

#### 5.2.1 Host System Preparation

Step 1: Install Docker

refer the [official Docs](https://docs.docker.com/get-started/get-docker/)


#### 5.2.2 Repository Setup

Step 1: Clone Repository

```bash
# Clone from GitHub
git clone https://github.com/kakalpa/PacketTracerWeb.git
cd PacketTracerWeb

# Verify directory structure
ls -la
# Expected: deploy.sh, add-instance.sh, remove-instance.sh, etc.
```

Step 2: Prepare Packet Tracer Installation File

```bash
# Copy Cisco Packet Tracer .deb to repository root
cp /path/to/CiscoPacketTracer.deb .

# Verify file
ls -lh CiscoPacketTracer.deb
# Expected: -rw-r--r-- ... 600M CiscoPacketTracer.deb (size varies)
```

#### 5.2.3 Configuration File Setup

Step 1: Create .env File

```bash
# Copy default configuration
cp .env.example .env


Step 2: Review Configuration

```bash
# Display current configuration
cat .env

# Edit as needed
nano .env  # or vim .env
```


### 5.3 First Deployment

#### 5.3.1 Initial Deployment

```bash
# Ensure correct directory
cd PacketTracerWeb

# Run deployment script
bash deploy.sh

# Expected output includes:
# - "Building ptvnc image..."
# - "Building pt-nginx image..."
# - "Step 1. Start MariaDB"
# - "Step 2. Start Packet Tracer VNC containers"
# - "Step 3. Import Guacamole Database"
# - "Step 4. Start Guacamole services"
# - "Step 5. Start Nginx web server"
# - "Step 6. Generating dynamic Guacamole connections"
# - "SUCCESS - Deployment and installation complete!"
```

#### 5.3.2 Deployment Time Expectations

- First deployment: 5-10 minutes (includes image building)
- Image building: 2-3 minutes
- Packet Tracer installation: 3-5 minutes
- Service startup: 1-2 minutes

#### 5.3.3 Verify Deployment Success

```bash
# Check all containers are running
docker ps

# Expected output:
# CONTAINER ID  IMAGE           STATUS          PORTS
# <id>          pt-nginx1       Up 2 minutes    0.0.0.0:80->80/tcp
# <id>          pt-guacamole    Up 2 minutes    
# <id>          pt-guacd        Up 2 minutes    
# <id>          ptvnc1          Up 3 minutes    
# <id>          ptvnc2          Up 3 minutes    
# <id>          guacamole-mariadb Up 3 minutes  

# Check Packet Tracer installation
docker exec ptvnc1 ls -l /opt/pt/packettracer

# Check Nginx configuration
docker exec pt-nginx1 nginx -t

# Check Guacamole connectivity
docker exec pt-guacamole curl -s http://localhost:8080/guacamole/ | head -20
```

### 5.4 Post-Installation Configuration

#### 5.4.1 Initial User Access

```bash
# Default Guacamole credentials
Username: ptadmin
Password: IlovePT

# Login URL
http://localhost/

# HTTPS URL (if enabled)
https://localhost/
```

#### 5.4.2 Network Configuration

```bash
# Check container IP addresses
docker inspect pt-guacamole | grep '"IPAddress"'

# Test network connectivity
docker exec pt-nginx1 ping ptvnc1 -c 3
docker exec pt-guacamole curl -s http://ptvnc1:5900
```

---

## 6. Configuration Management

### 6.1 Environment Variables (.env)

#### 6.1.1 Complete .env Reference

```bash
# ====================
# HTTPS Configuration
# ====================

# Enable or disable HTTPS
# true: Enable HTTPS, redirect HTTP to HTTPS
# false: HTTP only (default)
ENABLE_HTTPS=false

# Container-side path to SSL certificate
SSL_CERT_PATH=/etc/ssl/certs/server.crt

# Container-side path to SSL private key
SSL_KEY_PATH=/etc/ssl/private/server.key

# ====================
# GeoIP Configuration
# ====================

# Enable whitelist mode (allow only specified countries)
# true: Only allow specified countries
# false: Disable whitelist
NGINX_GEOIP_ALLOW=true

# Comma-separated country codes to allow
# Format: XX,YY,ZZ
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,FI

# Enable blacklist mode (block specified countries)
# true: Block specified countries
# false: Disable blacklist
NGINX_GEOIP_BLOCK=false

# Comma-separated country codes to block
# Format: XX,YY,ZZ
GEOIP_BLOCK_COUNTRIES=CN,RU,IR

# ====================
# Database Configuration
# ====================

# (Internal, typically not modified)
# MYSQL_DATABASE=guacamole_db
# MYSQL_USER=ptdbuser
# MYSQL_PASSWORD=ptdbpass
```

#### 6.1.2 Configuration Precedence

The system applies configurations in this order:

1. Environment variables (highest priority)
2. .env file values
3. Script hardcoded defaults (lowest priority)

#### 6.1.3 Configuration Validation

```bash
# Verify configuration is loaded
grep "ENABLE_HTTPS" .env

# Check active configuration
grep "NGINX_GEOIP_ALLOW" .env
grep "GEOIP_ALLOW_COUNTRIES" .env
```

### 6.2 Nginx Configuration

#### 6.2.1 Configuration File Structure

The ptweb.conf file is dynamically generated and includes:

```nginx
# HTTP Server Block (always included)
server {
    listen 80;
    # HTTP to HTTPS redirect (if ENABLE_HTTPS=true)
    # OR
    # Proxy configuration (if ENABLE_HTTPS=false)
}

# HTTPS Server Block (if ENABLE_HTTPS=true)
server {
    listen 443 ssl http2;
    ssl_certificate /etc/ssl/certs/server.crt;
    ssl_certificate_key /etc/ssl/private/server.key;
}

# Common Location Blocks
location ^~ /downloads/ { }
location ^~ /files { }
location / { }  # Guacamole proxy
```

#### 6.2.2 Modifying Nginx Configuration

```bash
# View current configuration
cat ptweb-vnc/pt-nginx/conf/ptweb.conf

# Manual modification (not recommended)
# Better approach: Modify generation function in deploy.sh

# Reload configuration without restart
docker exec pt-nginx1 nginx -s reload

# Full restart (causes brief downtime)
docker restart pt-nginx1
```

### 6.3 Database Configuration

#### 6.3.1 MariaDB Connection

```bash
# Connect to database directly
docker exec -it guacamole-mariadb mariadb -uroot -p

# Connect as Guacamole user
docker exec -it guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db
```

#### 6.3.2 Database Schema

```sql
# View all tables
USE guacamole_db;
SHOW TABLES;

# Check number of users
SELECT COUNT(*) FROM guacamole_user;

# List all connections
SELECT connection_id, connection_name, protocol FROM guacamole_connection;

# View user permissions
SELECT user_id, connection_id FROM guacamole_user_connection;
```

#### 6.3.3 Backup and Restore

```bash
# Backup database
docker exec guacamole-mariadb mariadb-dump -uroot -p guacamole_db > backup_$(date +%Y%m%d).sql

# Restore database
docker exec -i guacamole-mariadb mariadb -uroot -p guacamole_db < backup_20231102.sql

# Export schema only
docker exec guacamole-mariadb mariadb-dump --no-data -uroot -p guacamole_db > schema.sql
```

---

## 7. Security Features

### 7.1 GeoIP Access Control

#### 7.1.1 Allowlist Mode (Whitelist)

**Configuration**:
```bash
NGINX_GEOIP_ALLOW=true
GEOIP_ALLOW_COUNTRIES=US,CA,GB,AU,FI
NGINX_GEOIP_BLOCK=false
```

**Behavior**:
- Only users from allowed countries can connect
- All other connections are silently dropped (HTTP 444 No Response)
- Private IP ranges (127.0.0.0/8, 192.168.0.0/16, 10.0.0.0/8) are exempted

**Use Case**: Restrict access to specific regions for compliance

#### 7.1.2 Blocklist Mode (Blacklist)

**Configuration**:
```bash
NGINX_GEOIP_BLOCK=true
GEOIP_BLOCK_COUNTRIES=CN,RU,IR
NGINX_GEOIP_ALLOW=false
```

**Behavior**:
- Users from blocked countries are denied
- All other connections are allowed
- Useful for country-based restrictions

**Use Case**: Exclude specific high-risk regions

#### 7.1.3 Priority and Interaction

If both modes are enabled:

```
Check allow list first
    |
    +-- Country in allow list: ALLOW
    +-- Country not in allow list: CHECK BLOCK LIST
        |
        +-- Country in block list: DENY
        +-- Country not in block list: DENY
```

**Default Behavior**: If no filtering configured, allow all

### 7.3 Container Security

#### 7.3.1 Resource Limits

Default resource constraints per container:

- CPU: 0.1 cores (10% of single core)
- Memory: 1GB (adjustable via tune_ptvnc.sh)
- Process limit: 2048
- File descriptor limit: 1024

**Purpose**: Prevent resource exhaustion attacks

#### 7.3.2 Network Isolation

- Containers communicate through internal bridge network
- No external network access by default
- VNC ports not exposed to host network
- Database ports internal only

#### 7.3.3 User Permissions

- Packet Tracer runs as non-root user (ptuser)
- Database uses separate credentials
- Web server runs with minimal privileges

---

## 8. Deployment Procedures

### 8.1 Standard Deployment

#### 8.1.1 Fresh Deployment

```bash
# Navigate to repository
cd /path/to/PacketTracerWeb

# Configure settings
nano .env  # Review and adjust as needed

# Run deployment
bash deploy.sh

# Wait for completion
# Expected: ~5-10 minutes
```

#### 8.1.2 Recreate Deployment (Clean Slate)

```bash
# Full cleanup and redeploy
bash deploy.sh recreate

# This will:
# 1. Stop and remove all containers
# 2. Remove all volumes (DATA LOSS)
# 3. Redeploy fresh stack

# WARNING: All data is lost except /shared directory
```

### 8.2 Adding Instances

#### 8.2.1 Add Single Instance

```bash
# Add one more instance
bash add-instance.sh

# Creates: ptvnc3 (if ptvnc1, ptvnc2 exist)
# Updates: Nginx, Guacamole connections
# Time: 2-3 minutes
```

#### 8.2.2 Add Multiple Instances

```bash
# Add 5 instances at once
bash add-instance.sh 5

# Creates: ptvnc3, ptvnc4, ptvnc5, ptvnc6, ptvnc7
# Time: 10-15 minutes
```

#### 8.2.3 Instance Addition Process

```
Script Input
    |
    v
Determine new instance numbers
    |
    v
Start new ptvnc containers
    |
    v
Wait for Packet Tracer installation
    |
    v
Restart Guacamole services
    |
    v
Generate new connections
    |
    v
Restart Nginx proxy
    |
    v
Verify connectivity
    |
    v
Completion
```

### 8.3 Removing Instances

#### 8.3.1 Remove by Count

```bash
# Remove 1 instance (highest numbered)
bash remove-instance.sh

# Remove 3 instances
bash remove-instance.sh 3

# Removes: ptvnc5, ptvnc4, ptvnc3 (descending order)
```

#### 8.3.2 Remove Specific Instances

```bash
# Remove specific container
bash remove-instance.sh ptvnc2

# Remove multiple specific containers
bash remove-instance.sh ptvnc1 ptvnc3

# Removes specified instances only
```

#### 8.3.3 Removal Safety Considerations

- Active users are disconnected
- Unsaved work is lost
- User is not warned beforehand
- Best practice: Schedule during maintenance window

### 8.4 Performance Tuning

#### 8.4.1 Adjust Resource Allocation

```bash
# Increase memory to 2GB per container
bash tune_ptvnc.sh 2G 1

# Increase to 4GB memory, 2 CPU per container
bash tune_ptvnc.sh 4G 2

# Format: bash tune_ptvnc.sh <memory> <cpu>
```

#### 8.4.2 Performance Tuning Considerations

| Resource | Impact | Recommendation |
|----------|--------|-----------------|
| Memory | Packet Tracer performance, system stability | 1-2GB per instance |
| CPU | Responsiveness, simulation speed | 1 core per 2-3 instances |
| I/O | File access, network performance | Use SSD storage |
| Bandwidth | Multiple instances, VNC overhead | Dedicated 1Gbps minimum |

---

## 9. Operations and Maintenance

### 9.1 Monitoring and Health Checks

#### 9.1.1 Comprehensive Test Suite

```bash
# Run full health check (57 tests)
bash test-deployment.sh

# Tests cover:
# - Container status
# - Database connectivity
# - File sharing
# - Network connectivity
# - GeoIP configuration
# - HTTPS status
# - Service dependencies
```

#### 9.1.2 Manual Health Verification

```bash
# Check all containers running
docker ps -a

# Check container resource usage
docker stats

# Check Nginx logs
docker logs pt-nginx1 | tail -20

# Check application logs
docker logs pt-guacamole | tail -20

# Check database logs
docker logs guacamole-mariadb | tail -20
```

#### 9.1.3 Connectivity Testing

```bash
# Test HTTP access
curl -I http://localhost/

# Test HTTPS access (if enabled)
curl -k -I https://localhost/

# Test Guacamole backend
docker exec pt-nginx1 curl -s http://guacamole:8080/guacamole/ | head

# Test database
docker exec pt-guacamole curl -s http://guacamole-mariadb:3306
```

### 9.2 Backup and Recovery

#### 9.2.1 Backup Strategy

**Data to Backup**:
- MariaDB database (guacamole_db)
- User files (/shared directory)
- Custom configurations (.env)
- SSL certificates (./ssl)

#### 9.2.2 Backup Procedure

```bash
# Create backup directory
mkdir -p backups/$(date +%Y%m%d)

# Backup database
docker exec guacamole-mariadb mariadb-dump \
  -uroot -p guacamole_db > \
  backups/$(date +%Y%m%d)/guacamole_db.sql

# Backup shared files
cp -r shared/ backups/$(date +%Y%m%d)/shared

# Backup configuration
cp .env backups/$(date +%Y%m%d)/.env
cp -r ssl/ backups/$(date +%Y%m%d)/ssl

# Create archive
tar -czf backups/backup_$(date +%Y%m%d_%H%M%S).tar.gz \
  backups/$(date +%Y%m%d)/
```

#### 9.2.3 Recovery Procedure



# Restore database backup
docker exec -i guacamole-mariadb mariadb -uroot -p guacamole_db \
  < backups/20231102/guacamole_db.sql

# Restore shared files
rm -rf shared/
cp -r backups/20231102/shared .

# Restart services
bash deploy.sh
```

### 9.3 Logging and Audit Trail

#### 9.3.1 Log Locations

| Component | Log Location |
|-----------|-------------|
| Nginx | /var/log/nginx/access.log, error.log |
| Guacamole | Stdout (docker logs) |
| MariaDB | /var/log/mysql/error.log |
| Packet Tracer | ~/.PT-Prefs/VNClog.txt |

#### 9.3.2 Access Logging

```bash
# View HTTP access log
docker exec pt-nginx1 tail -50 /var/log/nginx/access.log

# View Nginx errors
docker exec pt-nginx1 tail -50 /var/log/nginx/error.log

# View Guacamole connections
docker exec pt-guacamole tail -50 logs/guacamole.log
```

#### 9.3.3 Security Audit

```bash
# Review connection attempts
docker exec pt-nginx1 grep "GET / HTTP" /var/log/nginx/access.log

# Check for failed authentication
docker exec pt-guacamole grep -i "authentication" logs/guacamole.log

# Review GeoIP blocks
docker exec pt-nginx1 grep "444" /var/log/nginx/error.log
```

---

## 10. Troubleshooting Guide

### 10.1 Common Issues and Solutions

#### 10.1.1 Containers Not Starting

**Symptom**: deployment.sh fails to start containers

**Diagnosis**:
```bash
# Check Docker daemon
sudo systemctl status docker

# Check disk space
df -h

# Review Docker errors
docker logs pt-nginx1 2>&1 | head -20
```

**Solutions**:
1. Ensure Docker daemon is running: `sudo systemctl start docker`
2. Free up disk space: `docker system prune`
3. Check .deb file: `ls -lh CiscoPacketTracer.deb`
4. Verify permissions: `sudo usermod -aG docker $USER`

#### 10.1.2 High Memory Usage

**Symptom**: Server becomes unresponsive, out of memory errors

**Diagnosis**:
```bash
# Check memory per container
docker stats

# Check host memory
free -h

# Check Packet Tracer memory usage
docker exec ptvnc1 ps aux | grep packettracer
```

**Solutions**:
1. Reduce instance count
2. Lower memory allocation: `bash tune_ptvnc.sh 1G 0.5`
3. Add more RAM to host
4. Enable swap (not recommended for performance)

#### 10.1.3 Network Connectivity Issues

**Symptom**: Cannot access web interface or containers not communicating

**Diagnosis**:
```bash
# Test container network
docker network ls
docker network inspect bridge

# Test DNS resolution
docker exec pt-nginx1 nslookup guacamole

# Test connectivity between containers
docker exec pt-nginx1 ping guacamole -c 3

# Check port mappings
docker ps --no-trunc
```

**Solutions**:
1. Restart Docker daemon: `sudo systemctl restart docker`
2. Recreate containers: `bash deploy.sh recreate`
3. Check firewall rules: `sudo ufw status`
4. Verify port availability: `sudo netstat -tlnp | grep 80`

#### 10.1.4 Slow VNC Access

**Symptom**: Laggy or unresponsive remote desktop

**Diagnosis**:
```bash
# Check network latency
docker exec pt-nginx1 ping ptvnc1 -c 10

# Check bandwidth usage
docker stats

# Check VNC server performance
docker exec ptvnc1 netstat -tulpn | grep 5900

# Check CPU usage
docker stats ptvnc1
```

**Solutions**:
1. Allocate more CPU: `bash tune_ptvnc.sh 2G 2`
2. Reduce screen resolution in VNC client
3. Disable visual effects in XFCE
4. Use compression in Guacamole settings
5. Check network bandwidth availability

#### 10.1.5 GeoIP Filtering Not Working

**Symptom**: GeoIP rules not blocking/allowing as configured

**Diagnosis**:
```bash
# Check GeoIP database
docker exec pt-nginx1 ls -lh /usr/share/GeoIP/

# Verify Nginx configuration
docker exec pt-nginx1 nginx -T | grep geoip

# Test with curl
curl -H "X-Forwarded-For: 1.2.3.4" http://localhost/

# Check access log
docker exec pt-nginx1 grep "1.2.3.4" /var/log/nginx/access.log
```

**Solutions**:
1. Verify .env configuration: `grep NGINX_GEOIP .env`
2. Restart Nginx: `docker restart pt-nginx1`
3. Regenerate configuration: `bash deploy.sh`
4. Check database file size: `docker exec pt-nginx1 stat /usr/share/GeoIP/GeoIP.dat`

### 10.2 Performance Optimization

#### 10.2.1 System-Level Optimization

```bash
# Enable kernel tuning
sudo sysctl -w net.core.somaxconn=65536
sudo sysctl -w net.ipv4.tcp_max_syn_backlog=65536

# Configure Docker daemon limits
sudo tee /etc/docker/daemon.json << EOF
{
  "storage-driver": "overlay2",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "live-restore": true
}
EOF

# Reload Docker
sudo systemctl restart docker
```

#### 10.2.2 Application-Level Optimization

```bash
# Increase Nginx worker processes
docker exec pt-nginx1 sed -i 's/worker_processes auto;/worker_processes 4;/' /etc/nginx/nginx.conf

# Adjust Guacamole heap size
docker exec pt-guacamole -e "GUACAMOLE_HOME=/config" -e "CATALINA_OPTS=-Xmx1024m"

# Tune Packet Tracer
docker exec ptvnc1 xfconf-query -c xsettings -p /Net/ThemeName -s Adwaita
```

---

## 11. Appendices

### Appendix A: Database Schema Reference

#### A.1 Core Tables

**guacamole_user**
```
Columns:
- user_id (INT): Primary key
- username (VARCHAR): Login name
- password_hash (VARCHAR): Encrypted password
- password_salt (BINARY): Salt for password hashing
- disabled (TINYINT): Account enabled/disabled
- expired (TINYINT): Password expiration status
- attributes (LONGTEXT): Custom attributes (JSON)
```

**guacamole_connection**
```
Columns:
- connection_id (INT): Primary key
- connection_name (VARCHAR): Display name
- parent_id (INT): Parent connection group
- protocol (VARCHAR): Protocol (vnc, rdp, ssh, etc.)
- max_connections (INT): Concurrent connections allowed
- max_connections_per_user (INT): Per-user limit
```

**guacamole_connection_parameter**
```
Columns:
- connection_parameter_id (INT): Primary key
- connection_id (INT): Foreign key to connection
- parameter_name (VARCHAR): Parameter name
- parameter_value (LONGTEXT): Parameter value
```

### Appendix B: Docker Commands Reference

#### B.1 Container Management

```bash
# List all containers
docker ps -a

# View container logs
docker logs <container_name>
docker logs -f <container_name>  # Follow log

# Execute command in container
docker exec <container_name> <command>
docker exec -it <container_name> /bin/bash

# Stop container
docker stop <container_name>

# Start container
docker start <container_name>

# Restart container
docker restart <container_name>

# Remove container
docker rm <container_name>
```

#### B.2 Image Management

```bash
# List images
docker images

# Build image
docker build -t image_name:tag .

# Remove image
docker rmi image_name:tag

# Tag image
docker tag source_image:tag target_image:tag

# Push to registry
docker push registry/image_name:tag
```

#### B.3 Volume Management

```bash
# List volumes
docker volume ls

# Inspect volume
docker volume inspect volume_name

# Remove volume
docker volume rm volume_name

# Backup volume
docker run --rm -v volume_name:/data -v $(pwd):/backup \
  alpine tar czf /backup/backup.tar.gz -C /data .
```

### Appendix C: Script Reference

#### C.1 deploy.sh Parameters

```bash
# Standard deployment
bash deploy.sh

# Recreate (full cleanup + redeploy)
bash deploy.sh recreate

# Custom number of instances
# (Edit numofPT variable in script before running)
```

#### C.2 add-instance.sh Parameters

```bash
# Add 1 instance
bash add-instance.sh

# Add 5 instances
bash add-instance.sh 5

# Add and specify base number
bash add-instance.sh 3
```

#### C.3 remove-instance.sh Parameters

```bash
# Remove 1 instance (highest number)
bash remove-instance.sh

# Remove 3 instances
bash remove-instance.sh 3

# Remove specific instances
bash remove-instance.sh ptvnc1 ptvnc3

# Remove by name pattern
bash remove-instance.sh ptvnc[1-3]
```

#### C.4 tune_ptvnc.sh Parameters

```bash
# Format: bash tune_ptvnc.sh <memory> <cpu>

# 1GB RAM, 0.5 CPU
bash tune_ptvnc.sh 1G 0.5

# 2GB RAM, 1 CPU
bash tune_ptvnc.sh 2G 1

# 4GB RAM, 2 CPU
bash tune_ptvnc.sh 4G 2
```

### Appendix D: File Structure

```
PacketTracerWeb/
├── deploy.sh                    # Main deployment script
├── add-instance.sh              # Add instances script
├── remove-instance.sh           # Remove instances script
├── tune_ptvnc.sh                # Resource tuning script
├── generate-dynamic-connections.sh  # Connection generator
├── test-deployment.sh           # Health check suite
├── generate-ssl-cert.sh         # Certificate generator
├── .env                         # Configuration file
├── README.md                    # Quick start guide
├── ptweb-vnc/
│   ├── Dockerfile               # Packet Tracer image definition
│   ├── db-dump.sql              # Guacamole schema
│   ├── docker-compose.yml       # Service composition (optional)
│   ├── pt-nginx/
│   │   ├── Dockerfile           # Nginx image definition
│   │   ├── conf/
│   │   │   ├── ptweb.conf       # Generated at runtime
│   │   │   ├── ptweb.conf.template  # Template file
│   │   │   └── nginx.conf       # Base nginx config
│   │   └── www/                 # Static web content
│   └── customizations/
│       ├── start                # Container startup script
│       ├── start-session        # VNC session start
│       ├── pt-install.sh        # Packet Tracer installer
│       ├── pt-detect.sh         # Packet Tracer detector
│       └── runtime-install.sh   # Runtime installation
├── shared/                      # User file sharing directory
├── ssl/                         # SSL certificates
│   ├── server.crt               # Certificate
│   └── server.key               # Private key
└── documents/
    └── COMPREHENSIVE_DOCUMENTATION.md  # This file
```

### Appendix E: Port Reference

| Port | Service | Protocol | Direction | Notes |
|------|---------|----------|-----------|-------|
| 80 | HTTP | TCP | Inbound | Exposed to internet |
| 443 | HTTPS | TCP | Inbound | Exposed to internet (if enabled) |
| 5900-5910 | VNC | TCP | Internal | Packet Tracer VNC servers |
| 8080 | Guacamole | HTTP | Internal | Application server |
| 4822 | Guacamole Daemon | TCP | Internal | Protocol handler |
| 3306 | MariaDB | TCP | Internal | Database server |

### Appendix F: Glossary

**Terms and Definitions**

- **Container**: Lightweight virtualization unit with isolated filesystem and processes
- **Docker**: Containerization platform for deploying applications
- **Image**: Blueprint or template for creating containers
- **Volume**: Persistent data storage for containers
- **Network**: Docker-managed network for inter-container communication
- **Nginx**: Web server and reverse proxy
- **Guacamole**: Clientless remote desktop gateway
- **VNC**: Virtual Network Computing protocol for remote desktop
- **GeoIP**: Geographic IP address database and lookup system
- **HTTPS/TLS**: Secure encrypted communication protocol
- **Bind Mount**: Host directory mounted into container
- **Named Volume**: Docker-managed persistent storage
- **DNS**: Domain Name System for service discovery
- **Bridge Network**: Docker internal network connecting containers

---

## Conclusion

The PacketTracerWeb system provides a comprehensive, scalable, and secure solution for delivering remote Cisco Packet Tracer access to distributed users. By leveraging containerization, web technologies, and modern security practices, it enables educational institutions and organizations to efficiently manage networking education and training environments.

The modular architecture allows for easy customization and extension, while the comprehensive documentation and testing capabilities ensure reliable and maintainable operations.

For additional support and updates, refer to the GitHub repository and community forums.

---

Document Version: 1.0
Date: November 2, 2025
Status: Complete and Comprehensive

