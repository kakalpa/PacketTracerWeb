# Docker Cleanup Scripts - Usage Guide

This guide explains the cleanup scripts available for managing your PacketTracer Docker deployment on remote servers.

## Overview

Two cleanup scripts are available in the `Scripts/` folder:

1. **`cleanup-all.sh`** - Safe cleanup without redeployment
2. **`cleanup-and-redeploy.sh`** - Cleanup + immediate fresh deployment

## ⚠️ Important Warning

**These scripts are destructive and cannot be undone!**

They will permanently delete:
- ✗ All running Docker containers (pt-nginx, guacamole, ptvnc1, ptvnc2, etc.)
- ✗ All Docker images (ptvnc, pt-nginx, pt-management, guacamole, mariadb)
- ✗ All Docker volumes (including the shared PacketTracer installation)
- ✗ All Docker build cache

## Usage on Remote Server

### Method 1: Cleanup Only

For times when you want to clean up without immediately redeploying:

```bash
cd /path/to/PacketTracerWeb
bash Scripts/cleanup-all.sh
```

**What it does:**
1. Stops all running containers
2. Removes all containers
3. Removes all Docker images
4. Removes all Docker volumes
5. Prunes Docker system and build cache
6. Shows remaining Docker resources
7. **Stops** (does not redeploy)

**After cleanup:**
- Your system is clean and ready for manual deployment
- You have time to copy a new .deb file if needed
- Simply run `bash deploy-full.sh` when ready to deploy

---

### Method 2: Cleanup + Redeploy (Recommended for Quick Reset)

For completely resetting your deployment in one command:

```bash
cd /path/to/PacketTracerWeb
bash Scripts/cleanup-and-redeploy.sh
```

**What it does:**
1. Displays warning about destructive actions
2. Asks for confirmation (type 'yes')
3. Stops all containers
4. Removes all containers, images, volumes, and cache
5. **Automatically starts `deploy-full.sh`**
6. Performs full fresh deployment

**Requirements:**
- `CiscoPacketTracer.deb` must be present in the repository root
- Run from the repository directory

**Timeline:**
- Cleanup: ~2-3 minutes
- Fresh deployment: ~5-10 minutes
- **Total time: 7-15 minutes**

---

## Step-by-Step Remote Server Deployment

### First-Time Setup (Recommended)

```bash
# 1. SSH to remote server
ssh user@remote-server

# 2. Navigate to repo (or clone if not present)
cd ~/PacketTracerWeb
# or: git clone https://github.com/kakalpa/PacketTracerWeb.git

# 3. Copy the latest PacketTracer .deb
# (Use SCP or your preferred method)
scp CiscoPacketTracer.deb user@remote:/path/to/repo/

# 4. Run the all-in-one script
bash Scripts/cleanup-and-redeploy.sh
```

### Subsequent Deployments/Resets

```bash
# Update repo to latest code
cd ~/PacketTracerWeb
git pull origin dev

# Copy new .deb if updated
scp CiscoPacketTracer.deb user@remote:/path/to/repo/

# Run cleanup + redeploy
bash Scripts/cleanup-and-redeploy.sh
```

---

## What's Different Between the Scripts

| Feature | cleanup-all.sh | cleanup-and-redeploy.sh |
|---------|---|---|
| Stops containers | ✓ | ✓ |
| Removes containers | ✓ | ✓ |
| Removes images | ✓ | ✓ |
| Removes volumes | ✓ | ✓ |
| Prunes cache | ✓ | ✓ |
| Redeploys automatically | ✗ | ✓ |
| Best for | Manual control | Quick reset |

---

## Safety Features

Both scripts include:

1. **Confirmation prompts** - You must confirm before proceeding
2. **Status checks** - Shows what's being removed
3. **Success verification** - Lists remaining resources after cleanup
4. **Error handling** - Continues even if some steps partially fail

Example confirmation prompt:
```
⚠️  WARNING: This will permanently delete:
  • All running Docker containers
  • All Docker images
  • All Docker volumes (including PacketTracer installation)
  • All Docker build cache

This action CANNOT be undone!

Are you absolutely sure? Type 'yes' to continue: _
```

---

## Troubleshooting

### Script Hangs or Takes Too Long

**Problem:** Script seems stuck at a step

**Solution:**
```bash
# Press Ctrl+C to stop
# Then manually check Docker status
docker ps -a
docker images
docker volume ls

# You can manually resume cleanup
```

### Permission Denied Error

**Problem:** `Permission denied: ./cleanup-all.sh`

**Solution:**
```bash
# Make scripts executable
chmod +x Scripts/cleanup-all.sh
chmod +x Scripts/cleanup-and-redeploy.sh

# Try again
bash Scripts/cleanup-all.sh
```

### .deb File Not Found (cleanup-and-redeploy.sh)

**Problem:** "CiscoPacketTracer.deb not found"

**Solution:**
```bash
# Copy the .deb file to repo root
cp /path/to/CiscoPacketTracer.deb .

# Verify it's there
ls -lh CiscoPacketTracer.deb

# Run script again
bash Scripts/cleanup-and-redeploy.sh
```

### Docker daemon not running

**Problem:** "Cannot connect to Docker daemon"

**Solution:**
```bash
# Start Docker
sudo systemctl start docker

# Verify it's running
docker ps

# Try cleanup again
bash Scripts/cleanup-all.sh
```

---

## Recommended Workflow for Remote Server

### Initial Deployment
```bash
bash Scripts/cleanup-and-redeploy.sh
```

### After Code Updates
```bash
git pull origin dev
bash Scripts/cleanup-and-redeploy.sh
```

### After PacketTracer Update (New .deb)
```bash
# Copy new .deb
scp new-CiscoPacketTracer.deb user@remote:~/PacketTracerWeb/

# Deploy
bash Scripts/cleanup-and-redeploy.sh
```

---

## What Happens After Cleanup?

After running `cleanup-all.sh`:
```
✓ Complete cleanup finished successfully!
═══════════════════════════════════════════════════════
Remaining Docker resources:
Containers: (none)
Images: (none)
Volumes: (none)

✓ System is now ready for a fresh deployment!

Next steps:
  1. Copy your PacketTracer .deb file to the repo root
  2. Run: bash deploy-full.sh
```

---

## Monitoring Cleanup Progress

Both scripts show real-time progress:

```
[1/5] Stopping all running containers...
✓ Stopped all running containers

[2/5] Removing all containers...
✓ Removed all containers

[3/5] Removing all Docker images...
✓ Removed all Docker images

[4/5] Removing all Docker volumes...
✓ Removed all Docker volumes

[5/5] Pruning Docker system and build cache...
✓ Pruned Docker system
```

---

## Questions & Support

**Q: Can I recover data after cleanup?**
A: No, the cleanup is permanent. Always backup important files before running.

**Q: How much disk space is freed?**
A: Typically 3-5 GB depending on image sizes and build cache.

**Q: Can I cancel the script mid-way?**
A: Yes, press Ctrl+C. Some cleanup may have already occurred.

**Q: What if only one container fails to remove?**
A: The script continues - it uses `|| true` to ignore errors on individual items.

**Q: Why delete volumes?**
A: Volumes contain the compiled PacketTracer installation. A fresh deployment ensures compatibility with the new .deb version.

---

## Script Locations

- **cleanup-all.sh**: `Scripts/cleanup-all.sh`
- **cleanup-and-redeploy.sh**: `Scripts/cleanup-and-redeploy.sh`

Both scripts are executable (chmod +x already applied).

---

## Commit History

- **Commit**: `3f60b96`
- **Message**: "Add comprehensive Docker cleanup scripts for fresh deployments"
- **Branch**: `dev`

Scripts added to repository on November 11, 2025.
