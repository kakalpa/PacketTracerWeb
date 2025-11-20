# Management Interface Fix - Bulk User Creation with VNC

## Issue Fixed

When bulk creating users through the management interface, containers were being created on the wrong network (`pt-stack` instead of `ptnet`), making them unreachable by Guacamole.

## Root Cause

The `pt-management/ptmanagement/api/routes.py` had two critical issues:

1. **Wrong Network**: Used `pt-stack` network instead of `ptnet`
2. **DNS Flag**: Added `--dns=127.0.0.1` which conflicted with Docker's embedded DNS

## Changes Made

### File: `pt-management/ptmanagement/api/routes.py`

**Change 1: Use correct network at startup**
```python
# BEFORE:
cmd = [
    'docker', 'run', '-d',
    '--name', container_name,
    '--dns=127.0.0.1',  # ❌ Wrong
    'ptvnc'
]
# Then later: docker network connect pt-stack  # ❌ Wrong network

# AFTER:
cmd = [
    'docker', 'run', '-d',
    '--name', container_name,
    '--network', 'ptnet',  # ✅ Correct network at startup
    'ptvnc'
]
# No network connect needed - already on ptnet
```

**Change 2: Removed redundant network connect**
- Deleted the `docker network connect pt-stack` call
- Removed DNS inspection logic that was no longer needed

## Connection Name Mapping

The database uses a logical mapping that **works correctly**:

```
Guacamole UI    → Database      → Actual Container
Connection Name   Hostname        Docker Name
═════════════════════════════════════════════════════
pt01            → ptvnc1:5901    → container: ptvnc1
pt02            → ptvnc2:5901    → container: ptvnc2
pt03            → ptvnc3:5901    → container: ptvnc3
pt04            → ptvnc4:5901    → container: ptvnc4
...
```

This design provides:
- ✅ Logical naming for connections (pt01, pt02, etc.)
- ✅ Flexible mapping to containers
- ✅ DNS-based hostname resolution on ptnet network
- ✅ No IP address dependency

## Verification

### Container Network Status
```bash
# All containers on ptnet with DNS resolution
docker ps | grep ptvnc
docker run --rm --network ptnet busybox ping ptvnc1  # ✅ Works
```

### VNC Port Accessibility
```bash
# guacd can reach all VNC ports
docker exec pt-guacd timeout 2 nc -zv ptvnc1 5901
# Connection to ptvnc1 (172.18.0.3) 5901 port [tcp/*] succeeded!
```

### Database Configuration
```sql
SELECT connection_name, parameter_value 
FROM guacamole_connection c 
LEFT JOIN guacamole_connection_parameter p 
ON c.connection_id = p.connection_id 
WHERE p.parameter_name = 'hostname'
ORDER BY connection_name;

-- Results:
-- pt01 | ptvnc1
-- pt02 | ptvnc2
-- pt03 | ptvnc3
-- etc.
```

### guacd Logs Show Successful Connections
```
guacd[1]: INFO: Creating new client for protocol "vnc"
guacd[71]: INFO: User joined connection (1 users now present)
guacd[71]: INFO: Local system reports 12 processor(s) available
guacd[71]: INFO: Graphical updates encoded using 12 worker threads
```

## Testing Workflow

### Bulk User Creation (via Management Interface)
1. Navigate to management interface: `http://localhost:5000`
2. Login with ptadmin credentials
3. Create bulk users with CSV upload
4. Each user gets assigned a ptvnc container
5. Connections auto-created: pt03, pt04, pt05, etc.

### Connect via Guacamole
1. Login to Guacamole: `http://localhost`
2. View user's assigned connections (pt01, pt02, etc.)
3. Click connection name to open VNC
4. Guacamole resolves hostname (ptvnc1, ptvnc2, etc.) via DNS
5. guacd connects to VNC port 5901 on correct container

## Architecture Notes

### Network Setup
- **ptnet**: Bridge network for all Guacamole services and ptvnc containers
- **pt-stack** (legacy): No longer used for new containers
- All services on same network for reliable DNS resolution

### Container Startup
- Containers join ptnet network **at creation time** (via `--network` flag)
- Docker's embedded DNS registers hostnames immediately
- No post-connection network attachment needed

### Scaling
- Add instances: `bash add-instance.sh 3` (adds ptvnc7, ptvnc8, ptvnc9)
- Bulk create users: Management interface automatically creates connections
- All instances automatically discoverable via DNS

## Related Commits
- Fix: Ensure all containers on ptnet network (add-instance.sh)
- Fix: Bulk user creation now uses correct ptnet network (pt-management)

## Testing Results
✅ 6 ptvnc containers on ptnet network  
✅ VNC ports 5901 accessible from guacd  
✅ DNS resolution working for all hostnames  
✅ Database connections properly configured  
✅ guacd logs show successful VNC handshakes  
✅ Management interface restarted on ptnet  

## Next Steps
1. Test bulk user creation with actual VNC connection
2. Monitor guacd logs for any connection errors
3. Verify Guacamole UI shows accessible connections
