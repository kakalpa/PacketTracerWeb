# Testing Checklist - .env Management Web UI

## Pre-Testing Setup

- [ ] Verify all implementation files are created
  - [ ] `pt-management/ptmanagement/api/env_config.py`
  - [ ] `pt-management/ptmanagement/api/env_routes.py`
  - [ ] `pt-management/templates/env_settings.html`
  - [ ] `pt-management/static/js/env-config.js`
  - [ ] `app.py` updated with blueprint registration
  - [ ] `dashboard.html` updated with settings link

- [ ] Clean Docker environment
  - [ ] Remove all old containers
  - [ ] Remove dangling volumes
  - [ ] Verify clean state

## Phase 1: Backend Unit Tests

### EnvConfigManager Tests

- [ ] **Test: File Detection**
  - [ ] Manager finds .env in multiple locations
  - [ ] Manager handles missing .env gracefully
  - [ ] Manager creates .env if missing
  - **Command to test:**
    ```bash
    docker exec pt-management python3 -c "
    from ptmanagement.api.env_config import EnvConfigManager
    mgr = EnvConfigManager()
    print(f'ENV Path: {mgr.env_file}')
    print(f'Path exists: {os.path.exists(mgr.env_file)}')
    "
    ```

- [ ] **Test: Read Configuration**
  - [ ] All config sections load correctly
  - [ ] Type conversion works (bool, list, int)
  - [ ] Default values handled properly
  - **Command to test:**
    ```bash
    docker exec pt-management python3 -c "
    from ptmanagement.api.env_config import EnvConfigManager
    mgr = EnvConfigManager()
    config = mgr.get_config()
    print('Config sections:', list(config.keys()))
    print('HTTPS enabled:', config['https']['enabled'])
    "
    ```

- [ ] **Test: Validation**
  - [ ] Valid config passes validation
  - [ ] Invalid rate format rejected
  - [ ] Invalid country codes rejected
  - [ ] Invalid cert paths handled
  - **Commands to test:**
    ```bash
    # Valid config
    docker exec pt-management python3 -c "
    from ptmanagement.api.env_config import EnvConfigManager
    mgr = EnvConfigManager()
    valid, msg = mgr.validate_config({'https': {'enabled': True}})
    print(f'Valid config: {valid}, Message: {msg}')
    "
    
    # Invalid rate format
    docker exec pt-management python3 -c "
    from ptmanagement.api.env_config import EnvConfigManager
    mgr = EnvConfigManager()
    valid, msg = mgr.validate_config({'rate_limit': {'enabled': True, 'rate': 'invalid'}})
    print(f'Invalid rate rejected: {not valid}')
    "
    ```

- [ ] **Test: Backup/Restore**
  - [ ] Backup created with timestamp
  - [ ] Backup file readable
  - [ ] Restore from backup works
  - [ ] Old backups cleaned up (keep last 10)
  - **Command to test:**
    ```bash
    docker exec pt-management python3 -c "
    from ptmanagement.api.env_config import EnvConfigManager
    mgr = EnvConfigManager()
    backup_path = mgr.backup_env()
    print(f'Backup created: {backup_path}')
    "
    ```

- [ ] **Test: Preview Changes**
  - [ ] Diff shows correct changes
  - [ ] Preview doesn't modify .env
  - [ ] Preview shows all modified sections
  - **Command to test:**
    ```bash
    docker exec pt-management python3 -c "
    from ptmanagement.api.env_config import EnvConfigManager
    mgr = EnvConfigManager()
    current = mgr.get_config()
    changes = {'https': {'enabled': not current['https']['enabled']}}
    preview = mgr.preview_changes(changes)
    print('Preview:', preview)
    "
    ```

## Phase 2: API Endpoint Tests

### Environment Configuration API

- [ ] **GET /api/env/config**
  - [ ] Returns 200 OK
  - [ ] Response contains all config sections
  - [ ] All values are correct type
  - [ ] Requires authentication
  - **Commands to test:**
    ```bash
    # Without auth (should fail)
    curl -v http://localhost:5000/api/env/config
    
    # With auth (after login)
    curl -b cookies.txt http://localhost:5000/api/env/config | python3 -m json.tool
    ```

- [ ] **GET /api/env/defaults**
  - [ ] Returns 200 OK
  - [ ] Works without authentication
  - [ ] Contains sample values for each config
  - **Command to test:**
    ```bash
    curl http://localhost:5000/api/env/defaults | python3 -m json.tool
    ```

- [ ] **POST /api/env/validate**
  - [ ] Returns 200 for valid config
  - [ ] Returns 400 for invalid config
  - [ ] Error message is clear
  - [ ] Requires authentication
  - **Command to test:**
    ```bash
    curl -b cookies.txt -X POST http://localhost:5000/api/env/validate \
      -H "Content-Type: application/json" \
      -d '{"https": {"enabled": true}}'
    ```

- [ ] **POST /api/env/preview**
  - [ ] Returns preview without applying changes
  - [ ] Shows diff correctly
  - [ ] .env file unchanged after preview
  - [ ] Requires authentication
  - **Command to test:**
    ```bash
    curl -b cookies.txt -X POST http://localhost:5000/api/env/preview \
      -H "Content-Type: application/json" \
      -d '{"https": {"enabled": true, "cert_path": "/etc/ssl/certs/cert.pem"}}'
    ```

- [ ] **POST /api/env/config**
  - [ ] Updates .env successfully
  - [ ] Creates backup before change
  - [ ] Validates before applying
  - [ ] Returns success message
  - [ ] Requires authentication
  - [ ] nginx reloaded (hot reload works)
  - **Command to test:**
    ```bash
    curl -b cookies.txt -X POST http://localhost:5000/api/env/config \
      -H "Content-Type: application/json" \
      -d '{"https": {"enabled": true}}' | python3 -m json.tool
    ```

- [ ] **POST /api/env/backup**
  - [ ] Creates backup
  - [ ] Returns backup filename
  - [ ] Backup file exists
  - [ ] Requires authentication
  - **Command to test:**
    ```bash
    curl -b cookies.txt -X POST http://localhost:5000/api/env/backup | python3 -m json.tool
    ```

- [ ] **GET /api/env/backups**
  - [ ] Lists available backups
  - [ ] Shows timestamp for each
  - [ ] Returns last 10 backups
  - [ ] Requires authentication
  - **Command to test:**
    ```bash
    curl -b cookies.txt http://localhost:5000/api/env/backups | python3 -m json.tool
    ```

- [ ] **POST /api/env/restore**
  - [ ] Restores configuration from backup
  - [ ] Validates backup path
  - [ ] Returns success message
  - [ ] nginx reloaded after restore
  - [ ] Requires authentication
  - **Command to test:**
    ```bash
    # Get backup path first
    BACKUP=$(curl -s -b cookies.txt http://localhost:5000/api/env/backups | python3 -c "import sys, json; data=json.load(sys.stdin); print(data['backups'][0]['path'])")
    
    # Restore
    curl -b cookies.txt -X POST http://localhost:5000/api/env/restore \
      -H "Content-Type: application/json" \
      -d "{\"backup_path\": \"$BACKUP\"}"
    ```

- [ ] **POST /api/env/nginx/regenerate**
  - [ ] Calls generate-nginx-conf.sh
  - [ ] Returns success/failure
  - [ ] nginx config updated
  - [ ] Requires authentication
  - **Command to test:**
    ```bash
    curl -b cookies.txt -X POST http://localhost:5000/api/env/nginx/regenerate | python3 -m json.tool
    ```

- [ ] **POST /api/env/nginx/reload**
  - [ ] Calls nginx -s reload
  - [ ] Returns success
  - [ ] nginx restarts without downtime
  - [ ] Requires authentication
  - **Command to test:**
    ```bash
    curl -b cookies.txt -X POST http://localhost:5000/api/env/nginx/reload | python3 -m json.tool
    ```

## Phase 3: Frontend UI Tests

### Page Load & Navigation

- [ ] **Test: Settings Page Accessible**
  - [ ] Navigate to /settings
  - [ ] Page loads with authentication
  - [ ] All tabs visible (HTTPS, GeoIP, Rate Limiting, Production, Backups)
  - [ ] Page returns 404 without authentication
  - **Browser test:**
    - Login to http://localhost:5000/
    - Click "Nginx Configuration" link
    - Verify page loads

- [ ] **Test: HTTPS Tab**
  - [ ] Enable/disable checkbox works
  - [ ] Cert path input accepts input
  - [ ] Key path input accepts input
  - [ ] Help text visible
  - **Browser test:**
    - Click HTTPS tab
    - Toggle enable checkbox
    - Enter cert/key paths
    - Verify fields update

- [ ] **Test: GeoIP Tab**
  - [ ] ALLOW mode checkbox toggles
  - [ ] BLOCK mode checkbox toggles
  - [ ] Country input accepts codes
  - [ ] Country tags appear and can be removed
  - [ ] Multiple countries can be added
  - **Browser test:**
    - Click GeoIP tab
    - Enable ALLOW mode
    - Type "US" and press Enter
    - Verify tag appears
    - Click X to remove
    - Add multiple countries

- [ ] **Test: Rate Limiting Tab**
  - [ ] Enable/disable checkbox works
  - [ ] Rate examples visible
  - [ ] Burst input accepts numbers
  - [ ] Zone size examples visible
  - **Browser test:**
    - Click Rate Limiting tab
    - Enable rate limiting
    - Verify rate format examples
    - Enter burst value

- [ ] **Test: Production Tab**
  - [ ] Mode toggle works
  - [ ] Public IP field shows/hides based on mode
  - [ ] IP input accepts valid formats
  - **Browser test:**
    - Click Production tab
    - Toggle production mode
    - Verify IP field visibility

- [ ] **Test: Backups Tab**
  - [ ] "Create Backup" button visible
  - [ ] Backup list loads
  - [ ] Each backup shows timestamp
  - [ ] Restore button visible on each backup
  - **Browser test:**
    - Click Backups tab
    - Click "Create Backup"
    - Verify new backup appears in list

### Form Interaction Tests

- [ ] **Test: Preview Changes**
  - [ ] "Preview Changes" button visible
  - [ ] Click opens modal
  - [ ] Modal shows what will change
  - [ ] Modal has "Apply" and "Cancel" buttons
  - [ ] Cancel closes modal without changes
  - **Browser test:**
    - Make config changes
    - Click "Preview Changes"
    - Verify modal appears with diff
    - Click "Cancel"

- [ ] **Test: Apply Configuration**
  - [ ] "Apply Configuration" button works
  - [ ] Spinner shows during apply
  - [ ] Success message appears
  - [ ] Form updates with new values
  - [ ] Changes persisted in .env
  - **Browser test:**
    - Make a config change (e.g., enable HTTPS)
    - Click "Apply Configuration"
    - Verify success message
    - Refresh page and verify change persists

- [ ] **Test: Reset Form**
  - [ ] "Reset" button works
  - [ ] Form reverts to saved values
  - [ ] Unsaved changes discarded
  - **Browser test:**
    - Make a config change
    - Click "Reset"
    - Verify form reverts to original values

- [ ] **Test: Create Manual Backup**
  - [ ] Button in Backups tab works
  - [ ] Backup created with timestamp
  - [ ] Backup appears in list
  - [ ] Backup filename follows pattern
  - **Browser test:**
    - Go to Backups tab
    - Click "Create Backup"
    - Verify new entry appears with current timestamp

- [ ] **Test: Restore Backup**
  - [ ] Restore button works
  - [ ] Confirmation before restore (optional)
  - [ ] Configuration restored from backup
  - [ ] Success message shown
  - [ ] Form updates with restored values
  - **Browser test:**
    - Create a backup
    - Make changes to config
    - Click restore on previous backup
    - Verify config restored

### Error Handling Tests

- [ ] **Test: Invalid Input Handling**
  - [ ] Invalid country code rejected
  - [ ] Invalid rate format rejected
  - [ ] Invalid cert path warned
  - [ ] Error messages clear
  - **Browser test:**
    - Enter invalid country code in GeoIP
    - Try to apply
    - Verify error message

- [ ] **Test: Network Error Handling**
  - [ ] Network timeout handled gracefully
  - [ ] Error message shown to user
  - [ ] Form state preserved
  - **Browser test:**
    - Disconnect network
    - Try to apply changes
    - Verify error handling

- [ ] **Test: Session Expiration**
  - [ ] Redirect to login if session expires
  - [ ] Settings link requires authentication
  - [ ] API endpoints return 401 when unauthenticated
  - **Browser test:**
    - Go to settings page
    - Delete session cookie
    - Refresh page
    - Verify redirect to login

## Phase 4: Integration Tests

### Docker Container Integration

- [ ] **Test: Docker Volume Mounting**
  - [ ] .env file accessible from container
  - [ ] Changes to .env visible on host
  - [ ] Host can read .env changes
  - **Commands to test:**
    ```bash
    # Check volume mount
    docker inspect pt-management | grep -A 5 "Mounts"
    
    # Write via API and verify on host
    cat /path/to/.env | grep HTTPS
    ```

- [ ] **Test: nginx Integration**
  - [ ] nginx reloads without errors
  - [ ] nginx stays online during reload
  - [ ] New config applied immediately
  - [ ] Old connections not dropped
  - **Commands to test:**
    ```bash
    # Check nginx before change
    curl -v http://localhost:80 2>&1 | head -20
    
    # Make change and apply via API
    curl -b cookies.txt -X POST http://localhost:5000/api/env/config \
      -H "Content-Type: application/json" \
      -d '{"https": {"enabled": true}}'
    
    # Verify nginx still responds
    curl -v http://localhost:80 2>&1 | head -20
    
    # Check nginx config validity
    docker exec pt-nginx1 nginx -t
    ```

- [ ] **Test: generate-nginx-conf.sh Integration**
  - [ ] Script called correctly
  - [ ] Script receives correct parameters
  - [ ] Config regenerated properly
  - [ ] No errors in nginx logs
  - **Commands to test:**
    ```bash
    # Check nginx config file
    docker exec pt-nginx1 cat /etc/nginx/conf.d/ptweb.conf | head -30
    
    # Check for GeoIP directive if enabled
    curl -b cookies.txt http://localhost:5000/api/env/config | grep -i geoip
    ```

### Database Integration

- [ ] **Test: User Authentication**
  - [ ] Only authenticated users can access settings
  - [ ] Admin decorator works
  - [ ] Non-admin users cannot write config
  - **Test via API:**
    ```bash
    # Try without auth
    curl http://localhost:5000/api/env/config
    
    # Try with non-admin user (if possible to create)
    # Should return 403 Forbidden
    ```

## Phase 5: Performance Tests

- [ ] **Test: Response Times**
  - [ ] GET /api/env/config < 200ms
  - [ ] POST /api/env/config < 500ms
  - [ ] GET /api/env/backups < 300ms
  - [ ] Page load < 2 seconds
  - **Commands to test:**
    ```bash
    time curl -b cookies.txt http://localhost:5000/api/env/config > /dev/null
    time curl -b cookies.txt -X POST http://localhost:5000/api/env/config \
      -H "Content-Type: application/json" \
      -d '{}' > /dev/null
    ```

- [ ] **Test: Large Configuration Updates**
  - [ ] System handles large country lists
  - [ ] No memory leaks
  - [ ] Backup system efficient
  - **Test:**
    ```bash
    # Add 50+ countries to GeoIP
    # Verify performance remains acceptable
    ```

## Phase 6: Security Tests

- [ ] **Test: Authentication Required**
  - [ ] All write endpoints require auth
  - [ ] All sensitive reads require auth
  - [ ] GET /api/env/defaults works without auth
  - [ ] Session hijacking prevented
  - **Commands to test:**
    ```bash
    # Try without auth
    curl -X POST http://localhost:5000/api/env/config
    
    # Should return 401 Unauthorized or redirect to login
    ```

- [ ] **Test: Input Validation**
  - [ ] SQL injection attempts rejected
  - [ ] Path traversal attempts blocked
  - [ ] XSS attempts sanitized
  - [ ] Large input rejected
  - **Test:**
    ```bash
    # Try path traversal
    curl -b cookies.txt -X POST http://localhost:5000/api/env/backup \
      -H "Content-Type: application/json" \
      -d '{"path": "../../etc/passwd"}'
    
    # Should fail or sanitize
    ```

- [ ] **Test: File Permissions**
  - [ ] .env file permissions correct (644)
  - [ ] Backups directory writable by container
  - [ ] No world-readable sensitive data
  - **Commands to test:**
    ```bash
    docker exec pt-management ls -la /app/.env
    docker exec pt-management ls -la /app/.env_backups/ | head -5
    ```

## Phase 7: Regression Tests

- [ ] **Test: Existing Functionality Unaffected**
  - [ ] Dashboard still works
  - [ ] User management still works
  - [ ] Container management still works
  - [ ] Authentication still works
  - [ ] Health check endpoint works
  - **Commands to test:**
    ```bash
    curl http://localhost:5000/health | python3 -m json.tool
    curl http://localhost:5000/api/users 2>&1 | head -20
    curl http://localhost:5000/api/containers 2>&1 | head -20
    ```

- [ ] **Test: Deployment Still Works**
  - [ ] deploy.sh still works
  - [ ] add-instance.sh still works
  - [ ] remove-instance.sh still works
  - [ ] No new dependencies required
  - **Manual test:**
    - Run full deployment
    - Verify all components start correctly

## Test Execution Order

1. **First**: Backend unit tests (5 min)
2. **Second**: API endpoint tests (10 min)
3. **Third**: Frontend UI tests (15 min)
4. **Fourth**: Integration tests (10 min)
5. **Fifth**: Security tests (5 min)
6. **Sixth**: Performance tests (5 min)
7. **Finally**: Regression tests (10 min)

**Total estimated time: 60 minutes**

## Success Criteria

✅ All tests pass without errors
✅ No regressions in existing functionality
✅ Performance meets requirements
✅ Security checks pass
✅ Documentation is complete
✅ Code is ready for commit

## Notes

- Keep terminal windows open to monitor logs
- Use `docker logs pt-management` to debug issues
- Use `docker logs pt-nginx1` to verify nginx changes
- Check `.env` file directly to verify changes
- Use browser developer console for frontend debugging

