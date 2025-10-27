# Packet Tracer - Web-Based Multi-Instance Deployment

Run multiple Cisco Packet Tracer instances in Docker containers with web-based access via Guacamole.

## 🚀 Quick Start

### Prerequisites
- Linux system with Docker installed
- Cisco Packet Tracer `.deb` installer (v9+)
- 4GB+ RAM available

### Installation
```bash
# 1. Clone the repository
git clone https://github.com/kakalpa/PacketTracerWeb.git
cd PacketTracerWeb

# 2. Place Packet Tracer .deb file in repo root
# (deploy.sh will automatically build the Docker image)

# 3. Run deployment
bash deploy.sh

# This will automatically:
# - Build the ptvnc Docker image (first time only)
# - Start MariaDB container
# - Start 2 Packet Tracer VNC containers
# - Configure Guacamole web interface
# - Generate web access endpoints

# 4. Open browser
http://localhost/

# 5. Login: ptadmin / IlovePT

# 6. Click connection (pt01, pt02, etc.) to access instance
```

---

## 📝 Available Scripts

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Initial deployment (creates 2 instances, builds Docker image if needed) |
| `add-instance.sh` | Add new instances dynamically (also builds image if missing) |
| `remove-instance.sh` | Remove instances safely |
| `tune_ptvnc.sh` | Adjust CPU/memory per container |
| `generate-dynamic-connections.sh` | Regenerate database connections |
| `test-deployment.sh` | Comprehensive health check (41 tests) |

### Automatic Image Building

Both `deploy.sh` and `add-instance.sh` automatically build the `ptvnc` Docker image if it doesn't exist:
- ✅ First deployment: Image is built automatically (Step 0)
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
- Then visit `http://localhost/downloads/`

## 🎯 Usage Examples

### Deploy (2 instances)
```bash
bash deploy.sh
# Creates: pt01, pt02
```

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

## ✅ Testing Deployment Health

After deployment, verify everything is working with the comprehensive test suite:

```bash
bash test-deployment.sh
```

This runs **41 tests** across 11 categories:
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

**Expected Output:** ✅ All 41 tests pass

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Container name conflict | `docker rm -f <container_name>` |
| Connections not showing | `bash generate-dynamic-connections.sh <count>` |
| Slow performance | `bash tune_ptvnc.sh 2G 1` |
| Tests failing | `bash test-deployment.sh` to identify issues |

---

## 📄 License

Cisco Packet Tracer installer not included. Place official copy in repo root. Using Packet Tracer implies acceptance of Cisco EULA.
