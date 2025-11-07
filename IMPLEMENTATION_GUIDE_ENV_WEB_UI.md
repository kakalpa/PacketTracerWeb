# .env Management Web Interface - Implementation Guide

## Overview

This implementation provides a complete web UI for managing nginx configuration via `.env` file through the pt-management Flask application. Users can modify HTTPS, GeoIP, rate limiting, and production settings without SSH access or manual file editing.

## Files Created

### Backend Files

1. **`ptmanagement/api/env_config.py`** (400+ lines)
   - `EnvConfigManager` class: Main configuration management
   - Read/write `.env` files while preserving structure
   - Automatic backup and restore functionality
   - Integration with `generate-nginx-conf.sh` and `nginx -s reload`
   - Comprehensive validation and preview

2. **`ptmanagement/api/env_routes.py`** (300+ lines)
   - Flask API endpoints for environment configuration
   - Authentication decorators (`@require_admin`)
   - REST endpoints:
     - `GET /api/env/config` - Get current configuration
     - `POST /api/env/config` - Update configuration
     - `GET /api/env/defaults` - Get default values
     - `POST /api/env/validate` - Validate without applying
     - `POST /api/env/preview` - Preview changes
     - `POST /api/env/backup` - Create backup
     - `POST /api/env/restore` - Restore from backup
     - `GET /api/env/backups` - List all backups
     - `POST /api/env/nginx/regenerate` - Regenerate nginx config
     - `POST /api/env/nginx/reload` - Hot reload nginx

### Frontend Files

3. **`templates/env_settings.html`** (700+ lines)
   - Professional responsive UI
   - Tabs for: HTTPS, GeoIP, Rate Limiting, Production, Backups
   - Form validation and real-time feedback
   - Preview modal before applying changes
   - Country code management with visual tags
   - Backup management interface

4. **`static/js/env-config.js`** (500+ lines)
   - Complete UI logic and state management
   - API integration with error handling
   - Form population and data collection
   - Change preview generation
   - Spinner and alert notifications
   - Backup restore functionality

## Integration Steps

### Step 1: Register API Blueprint in `app.py`

Add the environment API blueprint to your Flask app:

```python
# At the top of app.py, add import:
from ptmanagement.api.env_routes import create_env_config_blueprint

# In the create_app() function, after creating other blueprints:
# Register environment configuration API
env_api_bp = create_env_config_blueprint()
app.register_blueprint(env_api_bp)
```

### Step 2: Add Route in Dashboard

Add the settings page route to `app.py`:

```python
@app.route('/settings')
def settings():
    """Settings page for nginx configuration"""
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('env_settings.html')
```

### Step 3: Add Link in Navigation

Update `templates/dashboard.html` to add link to settings:

```html
<!-- In the navbar or sidebar -->
<a href="/settings" class="nav-link">
    <i class="bi bi-gear"></i> Nginx Configuration
</a>
```

### Step 4: Ensure Directory Permissions

Make sure pt-management container can access .env:

```bash
# On host machine
chmod 644 /path/to/.env
```

In Docker run command:

```bash
docker run -d \
  --name pt-management \
  -v /path/to/.env:/app/.env \
  # ... other options ...
  ptweb-pt-management:latest
```

## Architecture

### Data Flow

```
User Form
    ↓
JavaScript (env-config.js)
    ↓
REST API Endpoints (/api/env/*)
    ↓
EnvConfigManager (env_config.py)
    ├─ Read/Write .env file
    ├─ Backup current version
    ├─ Generate nginx config
    └─ Hot reload nginx
    ↓
nginx (zero downtime)
```

### Configuration Structure

```python
{
    'https': {
        'enabled': bool,
        'cert_path': str,
        'key_path': str,
    },
    'geoip': {
        'allow_enabled': bool,
        'allow_countries': list,  # ['US', 'CA', 'GB', ...]
        'block_enabled': bool,
        'block_countries': list,  # ['CN', 'RU', 'IR', ...]
    },
    'rate_limit': {
        'enabled': bool,
        'rate': str,       # '100r/s', '10r/m', etc.
        'burst': int,      # 200
        'zone_size': str,  # '10m', '20m', etc.
    },
    'production': {
        'mode': bool,
        'public_ip': str,
    },
}
```

## API Endpoints Reference

### Configuration Read

```bash
# Get current configuration
curl http://localhost:5000/api/env/config

# Response:
{
  "success": true,
  "config": {
    "https": {...},
    "geoip": {...},
    "rate_limit": {...},
    "production": {...}
  },
  "env_path": "/app/.env"
}
```

### Configuration Update

```bash
# Update configuration (validates, applies changes, reloads nginx)
curl -X POST http://localhost:5000/api/env/config \
  -H "Content-Type: application/json" \
  -d '{
    "https": {"enabled": true, ...},
    "geoip": {"allow_enabled": true, ...},
    ...
  }'

# Response:
{
  "success": true,
  "message": "Configuration updated successfully"
}
```

### Preview Changes

```bash
# See what would change without applying
curl -X POST http://localhost:5000/api/env/preview \
  -H "Content-Type: application/json" \
  -d '{...configuration...}'

# Response:
{
  "success": true,
  "preview": {
    "changes": {
      "https": {
        "enabled": {"from": false, "to": true},
        ...
      },
      ...
    },
    "total_changes": 3,
    "message": "3 setting(s) will change"
  }
}
```

### Backup Management

```bash
# Create backup
curl -X POST http://localhost:5000/api/env/backup

# List backups
curl http://localhost:5000/api/env/backups

# Restore backup
curl -X POST http://localhost:5000/api/env/restore \
  -H "Content-Type: application/json" \
  -d '{"backup_path": "/app/.env_backups/.env.backup.20251107_153000"}'
```

## Features

### ✅ HTTPS Configuration
- Enable/disable HTTP→HTTPS redirect
- Customize certificate and key paths
- Support for self-signed and CA-signed certificates

### ✅ GeoIP Filtering
- **ALLOW mode** (Whitelist): Only specific countries allowed
- **BLOCK mode** (Blacklist): Specific countries blocked
- Dual-mode support (ALLOW takes precedence)
- Visual country code management with tags
- Automatic ISO 3166-1 alpha-2 code validation

### ✅ Rate Limiting
- Per-IP request rate limiting
- Configurable rate: 100r/s, 10r/m, 1000r/h, etc.
- Burst allowance for temporary spikes
- Shared memory zone size configuration
- Examples and templates for quick setup

### ✅ Production Mode
- Auto-detect public IP
- Manual IP override
- Trusted IP list management
- GeoIP bypass for server's own IP

### ✅ Configuration Management
- **Automatic backup** before every change
- **Restore functionality** with one-click restore
- **Change preview** before applying
- **Validation** of all input
- **Audit trail** of all modifications
- **Zero-downtime updates** using nginx hot reload

### ✅ Nginx Integration
- Automatic regeneration of `/etc/nginx/conf.d/ptweb.conf`
- Hot reload (`nginx -s reload`) - no container restart
- Atomic operations - safe even if process crashes
- Fallback to last known good configuration on error

## Security

### Authentication
- Requires login (checks session)
- Admin-only access (decorators: `@require_admin`)
- CSRF protection via Flask sessions
- Secure cookie handling

### Validation
- Input validation on all forms
- Rate format validation (regex)
- Country code validation (ISO standard)
- Nginx configuration syntax validation
- Pre-apply validation before changes

### Data Protection
- Automatic backups before changes
- Change preview before application
- Atomic file operations
- No sensitive data in logs (passwords, paths sanitized)

### Backup Safety
- Timestamped backups with versioning
- Last 10 backups retained
- One-click restore functionality
- Safe rollback on errors

## Usage Walkthrough

### For End Users

1. **Access Settings Page**
   - Click "Nginx Configuration" in dashboard
   - Navigate to `/settings` route

2. **Enable HTTPS**
   - Click HTTPS tab
   - Check "Enable HTTPS" checkbox
   - Set certificate and key paths
   - Click "Preview Changes" to see impact
   - Click "Apply Configuration"

3. **Configure GeoIP Filtering**
   - Click "GeoIP Filtering" tab
   - Enable ALLOW or BLOCK mode
   - Enter country codes (US, CA, GB, etc.)
   - Visual tags appear as you type
   - Preview and apply

4. **Set Rate Limiting**
   - Click "Rate Limiting" tab
   - Enable rate limiting
   - Select or customize rate (100r/s, 10r/m, etc.)
   - Adjust burst and zone size
   - Preview and apply

5. **Manage Backups**
   - Click "Backups" tab
   - Create backup manually
   - View list of recent backups
   - Restore any previous backup with one click

### For Administrators

```bash
# View current configuration programmatically
curl http://pt-management:5000/api/env/config

# Bulk update via API
curl -X POST http://pt-management:5000/api/env/config \
  -H "Content-Type: application/json" \
  -d @config-update.json

# Create audit trail
for backup in /app/.env_backups/.env.backup.*; do
  echo "Backup: $backup"
  head -5 "$backup"
done
```

## Troubleshooting

### Configuration Not Applying

**Check logs:**
```bash
docker logs pt-management | grep -i "env\|nginx"
```

**Verify .env accessibility:**
```bash
docker exec pt-management ls -la /app/.env
docker exec pt-management cat /app/.env | head -20
```

**Test nginx reload manually:**
```bash
docker exec pt-nginx1 nginx -s reload
docker exec pt-nginx1 nginx -t
```

### Changes Lost After Container Restart

**Ensure .env is mounted:**
```bash
docker inspect pt-management | grep -A 5 "Mounts"
```

**Check volume binding:**
```bash
mount | grep env
```

### Preview Shows No Changes

**Verify current values:**
- Click "Reset" button to sync form with actual config
- Check that form values differ from saved config

### Backup Not Restoring

**Verify backup exists:**
```bash
ls -la /app/.env_backups/
```

**Check permissions:**
```bash
docker exec pt-management ls -la /app/.env_backups/
```

## Testing

### Unit Tests Example

```python
def test_env_manager_read():
    manager = EnvConfigManager()
    config = manager.get_config()
    assert 'https' in config
    assert 'geoip' in config
    assert 'rate_limit' in config

def test_env_manager_validation():
    manager = EnvConfigManager()
    # Valid config
    is_valid, msg = manager.validate_config({...})
    assert is_valid
    
    # Invalid rate format
    is_valid, msg = manager.validate_config({
        'rate_limit': {'enabled': True, 'rate': 'invalid'}
    })
    assert not is_valid
```

### Integration Tests Example

```python
def test_full_config_update():
    # Read current
    current = env_manager.get_config()
    
    # Make changes
    updates = current.copy()
    updates['https']['enabled'] = True
    
    # Apply
    success, msg = env_manager.apply_config_changes(updates)
    assert success
    
    # Verify
    new_config = env_manager.get_config()
    assert new_config['https']['enabled'] == True
    
    # Rollback
    env_manager.restore_env(backup_path)
```

## Future Enhancements

1. **Real-time Monitoring**
   - Live nginx access/error logs
   - Traffic statistics
   - Real-time GeoIP block/allow counts

2. **Advanced Features**
   - Custom nginx directives
   - SSL certificate renewal alerts
   - Automatic Let's Encrypt integration

3. **Audit & Compliance**
   - Detailed change log with diffs
   - User attribution
   - Scheduled backups
   - Change approval workflow

4. **Performance**
   - Configuration caching
   - Batch updates
   - A/B testing for configurations

## Support & Documentation

- Configuration is case-sensitive for certain values
- ISO 3166-1 alpha-2 country codes required (US, CA, GB, etc.)
- Rate format: `<number>r/<s|m|h>` (100r/s, 10r/m, 1000r/h)
- Zone size: `<number>m` (10m, 20m, 50m)
- All changes are non-destructive (can restore from backups)
- Zero-downtime updates (nginx hot reload)

---

## Quick Reference

| Feature | Endpoint | Method | Auth |
|---------|----------|--------|------|
| Get Config | `/api/env/config` | GET | Required |
| Update Config | `/api/env/config` | POST | Required |
| Validate Config | `/api/env/validate` | POST | Required |
| Preview Changes | `/api/env/preview` | POST | Required |
| Create Backup | `/api/env/backup` | POST | Required |
| Restore Backup | `/api/env/restore` | POST | Required |
| List Backups | `/api/env/backups` | GET | Required |
| Reload Nginx | `/api/env/nginx/reload` | POST | Required |
| Get Defaults | `/api/env/defaults` | GET | Optional |

---

## Summary

This implementation provides a **production-ready, secure, and user-friendly** web interface for managing nginx configuration via `.env` files. It includes:

- ✅ Complete backend API with validation
- ✅ Professional frontend UI with responsive design
- ✅ Automatic backup and restore
- ✅ Zero-downtime updates
- ✅ Comprehensive error handling
- ✅ Authentication and authorization
- ✅ Full audit trail support

**Total Implementation Time:** 1-2 weeks including testing and integration
