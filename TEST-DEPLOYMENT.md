# Test Deployment Script Guide

## Overview

`test-deployment.sh` is a comprehensive health check script that validates the entire Packet Tracer + Guacamole deployment across 11 test categories with 41 individual tests.

## Quick Start

```bash
# Run all tests
bash test-deployment.sh

# Expected output: ✅ ALL TESTS PASSED! DEPLOYMENT IS HEALTHY
```

## Test Categories

### 1. Docker Container Status (6 tests)
Verifies all required containers are running:
- MariaDB
- Guacd
- Guacamole
- Nginx
- ptvnc1
- ptvnc2

**What it checks:** Container state is "running"

### 2. Database Connectivity (4 tests)
Tests MariaDB and Guacamole database:
- MariaDB is accessible (can connect with credentials)
- Guacamole database exists
- Connections table exists
- At least 2 connections are configured

**What it checks:** Database accessibility and structure

### 3. Shared Folder Accessibility (4 tests)
Verifies `/shared/` directory exists in:
- Host filesystem
- ptvnc1 container
- ptvnc2 container
- Nginx container

**What it checks:** All containers have `/shared/` mounted

### 4. Shared Folder Write Permissions (3 tests)
Tests file write operations in `/shared/`:
- Host can create/delete files
- ptvnc1 can create/delete files
- ptvnc2 can create/delete files

**What it checks:** Write permissions are correct (777)

### 5. Desktop Symlinks (5 tests)
Verifies desktop shortcuts in Packet Tracer instances:
- ptvnc1 has Desktop directory
- ptvnc1 has "shared" symlink
- ptvnc1 symlink points to `/shared`
- ptvnc2 has "shared" symlink
- ptvnc2 symlink is accessible

**What it checks:** Easy access to shared folder from desktop

### 6. Web Endpoints (3 tests)
Tests HTTP endpoints:
- Guacamole root (`http://localhost/`) returns HTTP 200
- Downloads endpoint (`http://localhost/downloads/`) returns HTTP 200
- Directory listing works on `/downloads/`

**What it checks:** Web server configuration and Guacamole routing

### 7. File Download Workflow (5 tests)
End-to-end test of file save and download:
- Create test file in `/shared/` from host
- File visible from ptvnc1
- File visible from ptvnc2
- File downloadable via `http://localhost/downloads/`
- Downloaded content matches original

**What it checks:** Complete file sharing workflow

### 8. Helper Scripts (4 tests)
Verifies deployment helper scripts exist:
- deploy.sh
- add-instance.sh
- generate-dynamic-connections.sh (executable)
- tune_ptvnc.sh

**What it checks:** All utility scripts are present

### 9. Docker Volumes (2 tests)
Tests persistent storage:
- pt_opt named volume exists
- Packet Tracer installed in pt_opt

**What it checks:** Persistent installation across container recreations

### 10. Guacamole Database Schema (3 tests)
Validates database structure:
- guacamole_user table has data
- guacamole_connection table has connections
- guacamole_connection_parameter table has entries

**What it checks:** Database initialization and connection setup

### 11. Docker Networking (2 tests)
Tests inter-container communication:
- Guacamole can reach MariaDB
- Nginx can reach Guacamole

**What it checks:** Network connectivity between services

## Understanding Test Results

### ✅ All Tests Pass
```
Total Tests: 41
Passed: 41
Failed: 0

🎉 ALL TESTS PASSED! DEPLOYMENT IS HEALTHY
```
**Status:** Deployment is fully functional. All systems ready for use.

### ⚠️ Some Tests Fail
```
Total Tests: 41
Passed: 36
Failed: 5

⚠️ SOME TESTS FAILED - CHECK ERRORS ABOVE
```
**Status:** Some components need attention. See error messages for details.

## Common Issues and Solutions

### Issue: Container Not Running
**Error:** "Container X running... ❌ FAIL"

**Solutions:**
```bash
# Check container status
docker ps -a

# Restart container
docker restart <container_name>

# Full redeployment
bash deploy.sh
```

### Issue: Database Connectivity
**Error:** "MariaDB is accessible... ❌ FAIL"

**Solutions:**
```bash
# Check MariaDB logs
docker logs guacamole-mariadb

# Verify credentials (from deploy.sh)
docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass

# Restart MariaDB
docker restart guacamole-mariadb
```

### Issue: Shared Folder Not Found
**Error:** "Host /shared directory exists... ❌ FAIL"

**Solutions:**
```bash
# Create shared directory
mkdir -p $(pwd)/shared
chmod 777 $(pwd)/shared

# Re-create containers
bash deploy.sh
```

### Issue: Write Permissions Denied
**Error:** "Host can write to /shared... ❌ FAIL"

**Solutions:**
```bash
# Fix permissions
chmod 777 $(pwd)/shared

# Fix in containers
docker exec ptvnc1 chmod -R 777 /shared
docker exec ptvnc2 chmod -R 777 /shared
```

### Issue: Web Endpoint 404
**Error:** "Guacamole root endpoint (HTTP 200)... ❌ FAIL"

**Solutions:**
```bash
# Check nginx status
docker ps | grep nginx

# Check nginx logs
docker logs pt-nginx1

# Restart nginx
docker restart pt-nginx1

# Verify Guacamole is running
docker ps | grep guacamole
```

### Issue: File Download Fails
**Error:** "File downloadable via /downloads/... ❌ FAIL"

**Solutions:**
```bash
# Check /shared directory in nginx
docker exec pt-nginx1 ls -la /shared/

# Verify mount
docker inspect pt-nginx1 | grep -A 5 "Mounts"

# Restart nginx
docker restart pt-nginx1
```

## Running Specific Tests

You can edit `test-deployment.sh` to run only specific sections:

```bash
# Run only container status tests (Section 1)
# Comment out other sections in the script

# Or run tests individually
docker ps | grep mariadb  # Check container status
curl http://localhost/    # Check web endpoint
```

## Test Output Log

Each test outputs to `/tmp/test_output.log` temporarily. To see details of a failed test:

```bash
# Run test again
bash test-deployment.sh 2>&1 | grep -A 5 "FAIL"
```

## Performance

The test suite takes approximately **30-60 seconds** to complete, depending on system performance and network conditions.

## Troubleshooting Tips

1. **Run tests multiple times** - Transient network issues may cause false failures
2. **Check container logs** - `docker logs <container_name>` for detailed error messages
3. **Verify connectivity** - `docker network ls` and `docker network inspect bridge`
4. **Check disk space** - `df -h` to ensure adequate storage
5. **Monitor resources** - `docker stats` while tests run

## Integration with CI/CD

For automation, check exit code:

```bash
bash test-deployment.sh
if [ $? -eq 0 ]; then
    echo "Deployment healthy - proceed"
else
    echo "Deployment failed - investigate"
    exit 1
fi
```

## Questions or Issues?

Run tests with verbose output and share results:

```bash
bash test-deployment.sh 2>&1 | tee test-results.log
```

Share the `test-results.log` file for debugging.
