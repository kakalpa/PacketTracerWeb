# PT (Packet Tracer) multi-container deployment

This repository builds and runs multiple Cisco Packet Tracer instances inside Docker containers and exposes them through Guacamole + nginx.

Contents
- `ptweb-vnc/` - Docker build context for Packet Tracer containers and startup scripts
- `install.sh` - orchestrates building images, pulling required images, and starting containers

Quick start (local)
1. Place your Packet Tracer `.deb` installer next to `install.sh` (the script auto-detects common names).
2. Run the installer (this script will prompt for `YES`):

```bash
sudo bash ./install.sh
```

If you prefer to run unattended and capture logs:

```bash
printf 'YES\n' | sudo bash ./install.sh 2>&1 | tee ~/pt-install.log
tail -n 200 ~/pt-install.log
```

Push to GitHub
1. Create an empty repository on GitHub (via web UI or `gh repo create`).
2. Run the helper script to add the remote and push the current repository (no credentials embedded):

```bash
./push_to_github.sh <git-remote-url>
# Example (SSH): ./push_to_github.sh git@github.com:youruser/yourrepo.git
# Example (HTTPS): ./push_to_github.sh https://github.com/youruser/yourrepo.git
```

Performance tuning (PT instances are GUI apps inside containers; they can be heavy)

If PT instances feel slow, try the following (ordered by ease):

1) Increase container memory and CPU

For new containers, update the `startPT()` docker run line in `install.sh` to allocate more resources. Example:

```bash
docker run -d --name ptvnc$i --restart unless-stopped --cpus=1 -m 2G --ulimit nproc=4096 --ulimit nofile=4096 ptvnc
```

To update running containers (applies where supported):

```bash
sudo docker update --memory 2G --cpus 1 ptvnc1 ptvnc2
```

2) Reduce number of parallel instances per host

If you don't have enough RAM/CPU, reduce `numofPT` in `install.sh` (default set to a conservative 2). Run fewer containers per host or add more hosts.

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

If you want, I can provide an `install.sh` variant tuned for a bigger host (more memory & CPUs per container) or patch `install.sh` to accept environment variables for resource settings.

Troubleshooting
- If a container fails due to a name conflict, remove the old container: `sudo docker rm -f <name>`
- If you see `runuser: failed to execute /bin/bash: Resource temporarily unavailable`, make sure you've rebuilt the `ptweb-vnc` image after the `start-session` and Dockerfile changes. Rebuild with:

```bash
sudo env DOCKER_BUILDKIT=0 docker build ptweb-vnc -t ptvnc:fix
sudo docker tag ptvnc:fix ptvnc
```

License & notes
- The Cisco Packet Tracer installer is not included; use an official copy and place it in the repo root. Using Packet Tracer signifies acceptance of Cisco EULA.
