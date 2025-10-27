# PT (Packet Tracer) multi-container deployment - Access Packet Tracer Via the Browser

This Project is inspired by [[This Original Project](https://github.com/cnkang/ptremote)]

This repository builds and runs multiple Cisco Packet Tracer instances inside Docker containers and exposes them through Guacamole + nginx.

## 🚀 Installation Introduction

### What You'll Get
- Multiple Packet Tracer instances running in Docker containers
- Web-based access via Guacamole (no VNC client needed)
- Automated one-command deployment
- Offline/demo mode (no login required)

### Prerequisites
1. **Linux system** with Docker and Docker Compose installed
2. **Cisco Packet Tracer .deb installer** (Linux x64, version 9+)
3. **At least 4GB RAM** available

### Quick Installation
1. Place your Packet Tracer `.deb` file in the repository root
2. Run: `bash deploy.sh`
3. Open browser to: `http://localhost/guacamole/`
4. Use default credentials: `guacadmin` / `guacadmin`
5. Click Packet Tracer icon in the desktop to launch

---

## Contents
- `ptweb-vnc/` - Docker build context for Packet Tracer containers and startup scripts
- `deploy.sh` - Main deployment script (replaces old install.sh)

Performance tuning (PT instances are GUI apps inside containers; they can be heavy)

If PT instances feel slow, try the following (ordered by ease):

1) Increase container memory and CPU

Edit `deploy.sh` and update the docker run line to allocate more resources. Look for the section with:

```bash
docker run -d --name ptvnc$i --restart unless-stopped --cpus=0.1 -m 1G --ulimit nproc=2048 --ulimit nofile=1024 ptvnc
```

Change to:

```bash
docker run -d --name ptvnc$i --restart unless-stopped --cpus=1 -m 2G --ulimit nproc=4096 --ulimit nofile=4096 ptvnc
```

2) Reduce number of parallel instances per host

If you don't have enough RAM/CPU, reduce `numofPT` in `deploy.sh` (default set to 2). Run fewer containers per host or add more hosts.

3) Add swap / zram to give hosts more virtual memory

Example to create a 8G swap file (host):

```bash
sudo fallocate -l 8G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

4) Monitor and locate bottlenecks

Use these commands and check CPU/memory usage:

```bash
sudo docker stats --all
top -o %MEM
free -h
```

Look for containers using a lot of CPU or memory. If the host CPU is saturated, assign more CPUs to critical containers or reduce instance count.

5) Consider horizontal scaling or dedicated hosts

If you need many concurrent PT users, deploy on multiple hosts (or scale with Kubernetes) so each host holds a few PT instances.

Troubleshooting
- If a container fails due to a name conflict, remove the old container: `sudo docker rm -f <name>`
- If you see `runuser: failed to execute /bin/bash: Resource temporarily unavailable`, make sure you've rebuilt the `ptweb-vnc` image after the `start-session` and Dockerfile changes. Rebuild with:

```bash
sudo env DOCKER_BUILDKIT=0 docker build ptweb-vnc -t ptvnc:fix
sudo docker tag ptvnc:fix ptvnc
```

License & notes
- The Cisco Packet Tracer installer is not included; use an official copy and place it in the repo root. Using Packet Tracer signifies acceptance of Cisco EULA.
