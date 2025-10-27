# Packet Tracer - Web-Based Multi-Instance Deployment

Run multiple Cisco Packet Tracer instances in Docker containers with web-based access via Guacamole.

## 🚀 Quick Start

### Prerequisites
- Linux system with Docker installed
- Cisco Packet Tracer `.deb` installer (v9+)
- 4GB+ RAM available

### Installation
```bash
# 1. Place Packet Tracer .deb file in repo root
# 2. Run deployment
bash deploy.sh

# 3. Open browser
http://localhost/guacamole/

# 4. Login: guacadmin / guacadmin
# 5. Click connection (pt01, pt02, etc.)
# 6. Click Packet Tracer icon on desktop
```

---

## 📝 Available Scripts

| Script | Purpose |
|--------|---------|
| `deploy.sh` | Initial deployment (creates 2 instances) |
| `add-instance.sh` | Add new instances dynamically |
| `tune_ptvnc.sh` | Adjust CPU/memory per container |
| `generate-dynamic-connections.sh` | Regenerate database connections |

---

## 🎯 Usage Examples

### Deploy (2 instances)
```bash
bash deploy.sh
# Creates: pt01, pt02
```

### Add Instances
```bash
bash add-instance.sh      # Auto-adds next instance (pt03)
bash add-instance.sh 5    # Scale to 5 instances (pt01-pt05)
```
Automatically restarts services and updates web interface.

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

## ⚡ Performance Tuning

Packet Tracer instances consume significant resources. If slow:

**Option 1: Increase resources (Recommended)**
```bash
bash tune_ptvnc.sh 2G 1    # 2GB RAM, 1 CPU per container
```

**Option 2: Reduce instances**
Edit `deploy.sh`, change `numofPT=2` to `numofPT=1` and redeploy.

**Option 3: Monitor usage**
```bash
docker stats --all
```

---

## 🐛 Troubleshooting

| Issue | Solution |
|-------|----------|
| Container name conflict | `docker rm -f <container_name>` |
| Connections not showing | `bash generate-dynamic-connections.sh <count>` |
| Slow performance | `bash tune_ptvnc.sh 2G 1` |

---

## 📄 License

Cisco Packet Tracer installer not included. Place official copy in repo root. Using Packet Tracer implies acceptance of Cisco EULA.
