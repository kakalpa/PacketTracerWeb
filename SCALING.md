# Scaling & Management Guide

## Overview

This guide explains how to safely scale your Packet Tracer deployment up or down, and what happens to users during scaling operations.

## Quick Reference

```bash
# View current instances
docker ps --format "table {{.Names}}" | grep "^ptvnc"

# Add instances
bash add-instance.sh      # Add 1 instance
bash add-instance.sh 3    # Add 3 instances

# Remove instances
bash remove-instance.sh   # Remove 1 instance
bash remove-instance.sh 2 # Remove 2 instances

# Verify health after scaling
bash test-deployment.sh
```

---

## Adding Instances

### Why Add Instances?
- Accommodate more concurrent users
- Distribute load across multiple containers
- Each instance runs independently

### How to Add Instances

```bash
bash add-instance.sh      # Add 1 more instance
bash add-instance.sh 5    # Add 5 more instances
```

### What Happens During Add

1. **Removes old Guacd** - Stops and removes old guacamole service discovery daemon
2. **Creates new ptvnc containers** - One per instance requested
3. **Restarts Guacd** - With links to all ptvnc containers (old + new)
4. **Recreates Guacamole** - Web service for VNC access
5. **Recreates Nginx** - Reverse proxy and file download server
6. **Regenerates Connections** - Updates database with new instance connections

### Important: User Impact

⚠️ **Active users will be disconnected** during this process:

- **VNC connections drop** - Guacamole sessions end
- **Browser shows error** - Connection lost message
- **Unsaved work is lost** - Files in Packet Tracer may be lost
- **Users must refresh** - They need to reload and reconnect

### Recommended Process

```
1. Announce: "Scaling maintenance in 5 minutes"
2. Wait: Give users time to save and exit
3. Verify: No active connections
4. Scale: bash add-instance.sh N
5. Verify: bash test-deployment.sh
6. Announce: "System ready"
```

### Example: Add 3 Instances

```bash
# Before: pt01, pt02 (2 instances)
docker ps | grep ptvnc
# Output: ptvnc2, ptvnc1

# Run
bash add-instance.sh 3

# After: pt01-pt05 (5 instances)
docker ps | grep ptvnc
# Output: ptvnc5, ptvnc4, ptvnc3, ptvnc2, ptvnc1

# Available in Guacamole: pt01, pt02, pt03, pt04, pt05
```

---

## Removing Instances

### Why Remove Instances?

- Free up system resources
- Decommission unused instances
- Downsize during off-peak times
- Handle instance failures

### How to Remove Instances

Three modes available:

#### Mode 1: Remove by Count (Highest First)
```bash
bash remove-instance.sh   # Remove 1 instance (highest number)
bash remove-instance.sh 2 # Remove 2 instances
bash remove-instance.sh 3 # Remove 3 instances
```

#### Mode 2: Remove Specific Instance
```bash
bash remove-instance.sh pt02    # Remove specific instance pt02
bash remove-instance.sh pt05    # Remove specific instance pt05
```

#### Mode 3: Remove Multiple Specific Instances
```bash
bash remove-instance.sh pt02 pt04          # Remove pt02 and pt04
bash remove-instance.sh pt01 pt03 pt05     # Remove pt01, pt03, pt05
```

### What Gets Removed

**Count Mode (Default):**
- Removes highest-numbered instances first
- `bash remove-instance.sh 2` removes pt05, then pt04
- Useful for simple "remove N instances" requests

**Specific Name Mode:**
- Removes only the specified instances by name
- `bash remove-instance.sh pt02` removes only pt02
- Useful for decommissioning specific instances
- Supports multiple names: `bash remove-instance.sh pt02 pt04 pt05`

**Mixed Mode:**
- Accepts both count and instance names
- If all arguments are instance names (ptXX format): uses specific mode
- If any argument is numeric: uses count mode

### What Happens During Remove

1. **Confirmation Prompt** - Shows which instances will be removed
2. **Stops Containers** - Terminates selected ptvnc containers
3. **Stops Guacd** - Removes old service discovery
4. **Restarts Guacd** - With remaining instances only
5. **Recreates Guacamole** - Updates web service
6. **Recreates Nginx** - Updates reverse proxy
7. **Regenerates Connections** - Removes old connections from database

### Important: User Impact

⚠️ **Same as adding instances** - Users will be disconnected

### Recommended Process

```bash
# Before removing, announce downtime
echo "System maintenance - scaling down"

# Verify no active users
curl http://localhost/  # Should work
bash test-deployment.sh # Verify health before

# Remove instances
bash remove-instance.sh 2  # Remove 2 instances

# Verify after
bash test-deployment.sh

# Announce ready
echo "System ready"
```

### Example: Remove 2 Instances

```bash
# Before: ptvnc1-ptvnc5 (5 instances)
bash remove-instance.sh 2

# After: ptvnc1-ptvnc3 (3 instances)
# Removed: ptvnc5, ptvnc4 (highest numbers first)
```

---

## Understanding Impact on Users

### During Scaling Operations

The following happens automatically:

| Component | Status | User Impact |
|-----------|--------|-------------|
| **Guacamole (Web Server)** | Recreated | Browser connection lost |
| **Nginx (Proxy)** | Recreated | Cannot access `http://localhost/` |
| **VNC Streams** | Terminated | Packet Tracer desktop disconnects |
| **User Session** | Lost | Must log back in |
| **Unsaved Work** | Lost | Files not in `/shared/` are gone |

### Why This Happens

Current architecture uses Docker `--link` containers:
- Links are destroyed when containers recreate
- Docker doesn't support live migration of links
- VNC sessions can't transfer between containers
- Guacamole sessions are in-memory (not persistent)

### Workarounds

**Option 1: Save to /shared/ (Recommended)**
- Users save files to `/shared/` instead of local `/home/`
- Files survive container recreation
- Accessible at `http://localhost/downloads/`

**Option 2: Scale During Off-Hours**
- Run `add-instance.sh` or `remove-instance.sh` at night
- No users affected
- Safer approach

**Option 3: Future Enhancement**
- Use Docker Compose with named networks (instead of `--link`)
- Use persistent session storage for Guacamole
- Would allow zero-downtime scaling

---

## Monitoring and Testing

### Before Scaling

```bash
# Check health
bash test-deployment.sh

# Check active connections
curl http://localhost/  # Should return 200

# Check current instances
docker ps --format "table {{.Names}}" | grep ptvnc
```

### After Scaling

```bash
# Test all components
bash test-deployment.sh

# Verify instances created/removed
docker ps --format "table {{.Names}}" | grep ptvnc

# Check Guacamole has new connections
curl http://localhost/guacamole/api/session/data/mysql

# Verify file download still works
curl http://localhost/downloads/ | grep "Index of"
```

### Troubleshooting

**Issue: Tests fail after scaling**
```bash
# Full health check
bash test-deployment.sh

# Check logs
docker logs pt-guacamole
docker logs pt-nginx1
docker logs pt-guacd
```

**Issue: New instances not showing in Guacamole**
```bash
# Regenerate connections manually
bash generate-dynamic-connections.sh 5  # For 5 instances

# Restart Guacamole
docker restart pt-guacamole
```

**Issue: Can't access web interface after scaling**
```bash
# Restart nginx
docker restart pt-nginx1

# Or recreate it
docker rm -f pt-nginx1
# Run: docker run ... (from add-instance.sh)
```

---

## Best Practices

### ✅ DO

- ✅ Save work to `/shared/` before scaling
- ✅ Run tests after scaling
- ✅ Notify users before scaling
- ✅ Scale during off-hours
- ✅ Keep at least 1 instance running
- ✅ Monitor `test-deployment.sh` results

### ❌ DON'T

- ❌ Scale while users are connected
- ❌ Remove all instances at once
- ❌ Quickly scale up/down repeatedly
- ❌ Ignore test failures after scaling
- ❌ Scale without backup/planning
- ❌ Run both add and remove simultaneously

---

## Command Reference

### Add Instances

```bash
# Add 1 instance (default)
bash add-instance.sh

# Add specific count
bash add-instance.sh 1    # Add 1 instance
bash add-instance.sh 2    # Add 2 instances
bash add-instance.sh 5    # Add 5 instances
bash add-instance.sh 10   # Add 10 instances

# Example: Scale from 2 to 5 instances
bash add-instance.sh 3    # Adds pt03, pt04, pt05
```

### Remove Instances

#### By Count (Highest First)
```bash
# Remove 1 instance (default)
bash remove-instance.sh

# Remove specific count
bash remove-instance.sh 1 # Remove highest numbered instance
bash remove-instance.sh 2 # Remove 2 highest numbered instances
bash remove-instance.sh 3 # Remove 3 highest numbered instances

# Example: Scale from 5 to 2 instances
bash remove-instance.sh 3 # Removes pt05, pt04, pt03
```

#### By Specific Instance Name
```bash
# Remove single instance by name
bash remove-instance.sh pt02    # Remove only pt02
bash remove-instance.sh pt05    # Remove only pt05

# Remove multiple specific instances
bash remove-instance.sh pt02 pt04          # Remove pt02 and pt04
bash remove-instance.sh pt01 pt03 pt05     # Remove pt01, pt03, pt05

# Example: Remove damaged instance
bash remove-instance.sh pt03    # Remove the specific problem instance
```

#### Comparison: Count vs Name Mode

| Need | Command | Removes |
|------|---------|---------|
| Remove highest 1 | `bash remove-instance.sh` | pt05 |
| Remove highest 3 | `bash remove-instance.sh 3` | pt05, pt04, pt03 |
| Remove specific | `bash remove-instance.sh pt02` | pt02 only |
| Remove specific + highest | `bash remove-instance.sh pt02 pt04` | pt02, pt04 |

### Verify State

```bash
# Test everything
bash test-deployment.sh

# Check instances
docker ps --format "table {{.Names}}" | grep ptvnc

# Check connections in DB
docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -e \
  "SELECT connection_name FROM guacamole_connection ORDER BY connection_name;"
```

---

## Frequently Asked Questions

**Q: Will I lose my files when scaling?**
A: Only files in `/shared/` are preserved. Everything in `/home/` is lost. Always save to `/shared/`.

**Q: Can I add and remove at the same time?**
A: No, run them separately. Recommend: add all needed instances first, then remove.

**Q: What's the maximum number of instances?**
A: Depends on system resources. Use `bash tune_ptvnc.sh` to adjust per-instance limits.

**Q: Do I need to restart anything after scaling?**
A: No, the scripts handle all restarts automatically.

**Q: Can scaling happen without disconnecting users?**
A: Not with current architecture. Use Docker Compose or load balancer for zero-downtime scaling.

**Q: How often can I scale?**
A: Scale as needed, but recommended: once per maintenance window to avoid confusing users.

---

## Support

For issues, run:

```bash
# Full diagnostics
bash test-deployment.sh 2>&1 | tee diagnostics.log

# Share the diagnostics file for support
```
