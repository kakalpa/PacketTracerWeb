# HTTPS Configuration for Management Console

This guide explains how to enable HTTPS for the `pt-management` console (admin dashboard).

## Overview

The management console now supports both **HTTP** and **HTTPS** modes:
- **HTTP (insecure)** - Port 5000 (default, no certificate needed)
- **HTTPS (secure)** - Port 5443 (requires SSL certificate)

Both the Nginx reverse proxy (Guacamole) and pt-management console can be individually configured for HTTPS.

---

## Quick Start: Enable HTTPS

### Step 1: Generate SSL Certificates

If you don't have SSL certificates, generate self-signed certificates:

```bash
bash generate-ssl-cert.sh
```

This creates:
- `ssl/server.crt` - Certificate
- `ssl/server.key` - Private key
- Valid for 365 days

### Step 2: Enable HTTPS in .env

Edit `.env` and set:

```bash
ENABLE_HTTPS=true
SSL_CERT_PATH=/etc/ssl/certs/server.crt
SSL_KEY_PATH=/etc/ssl/private/server.key
```

### Step 3: Deploy

```bash
# Full deployment with HTTPS
bash deploy-full.sh recreate
```

### Step 4: Access

- **Guacamole (web UI)**: `https://localhost`
- **pt-management (admin)**: `https://localhost:5443`

---

## Management Script

Use `manage-https.sh` to quickly enable/disable/check HTTPS status:

```bash
# Enable HTTPS
bash manage-https.sh enable

# Disable HTTPS (use HTTP only)
bash manage-https.sh disable

# Check current status
bash manage-https.sh status
```

---

## How It Works

### Deployment Flow (deploy-full.sh)

1. **Reads `.env`** for `ENABLE_HTTPS` setting
2. **Checks for certificates** at `./ssl/server.crt` and `./ssl/server.key`
3. **Mounts certificates** into containers if found
4. **Passes environment variables** to pt-management container
5. **pt-management startup script** decides:
   - If HTTPS enabled AND certificates present → start on port 5443 with HTTPS
   - Otherwise → start on port 5000 with HTTP

### pt-management Dockerfile

The startup logic is embedded in `start.sh`:

```bash
if [ "$ENABLE_HTTPS" = "true" ] && [ -f "$SSL_CERT" ] && [ -f "$SSL_KEY" ]; then
  # Start on port 5443 with HTTPS
  exec gunicorn \
    --bind 0.0.0.0:5443 \
    --certfile="$SSL_CERT" \
    --keyfile="$SSL_KEY" \
    --workers 2 \
    --timeout 120 \
    wsgi:app
else
  # Start on port 5000 with HTTP
  exec gunicorn \
    --bind 0.0.0.0:5000 \
    --workers 2 \
    --timeout 120 \
    wsgi:app
fi
```

---

## Configuration Examples

### Example 1: HTTPS for Both Services

```bash
# .env
ENABLE_HTTPS=true
SSL_CERT_PATH=/etc/ssl/certs/server.crt
SSL_KEY_PATH=/etc/ssl/private/server.key
```

Result:
- Nginx: http://localhost (redirects to https://localhost)
- Nginx: https://localhost:443 ✓
- pt-management: http://localhost:5000 (redirects to https://localhost:5443)
- pt-management: https://localhost:5443 ✓

### Example 2: HTTP Only (Development)

```bash
# .env
ENABLE_HTTPS=false
```

Result:
- Nginx: http://localhost:80 ✓
- pt-management: http://localhost:5000 ✓
- No SSL/TLS required

---

## Port Mapping

| Service | HTTP | HTTPS |
|---------|------|-------|
| Nginx (Guacamole) | 80 | 443 |
| pt-management | 5000 | 5443 |

All ports are mapped from container to host (same port numbers).

---

## Using Production Certificates

To use real certificates (not self-signed):

1. **Place your certificates** in `./ssl/`:
   - `ssl/server.crt` (certificate)
   - `ssl/server.key` (private key)

2. **Set .env**:
   ```bash
   ENABLE_HTTPS=true
   ```

3. **Deploy**:
   ```bash
   bash deploy-full.sh
   ```

The deployment will automatically mount your certificates into both containers.

---

## Troubleshooting

### Certificates not found but HTTPS enabled

```bash
# Check certificate files
ls -la ssl/

# If missing, generate:
bash generate-ssl-cert.sh
```

### HTTP connection in browser despite enabling HTTPS

**Cause**: Certificates not found  
**Solution**:
```bash
bash generate-ssl-cert.sh
bash deploy-full.sh recreate
```

### Certificate warnings in browser

This is **normal for self-signed certificates**. Your browser will warn you. To bypass:
- **Chrome**: Click "Advanced" → "Proceed to localhost"
- **Firefox**: Click "Advanced" → "Accept the Risk and Continue"

### Check HTTPS status

```bash
# Show current configuration
bash manage-https.sh status

# Verify container port mappings
docker port pt-management
docker port pt-nginx1

# Test connection
curl -k https://localhost:5443/health
curl https://localhost/
```

### Restart after HTTPS changes

```bash
# Restart management console only
docker restart pt-management

# Or full redeployment
bash deploy-full.sh recreate
```

---

## Docker Command Reference

### Manual HTTPS Start

```bash
# Build image
docker build -t pt-management pt-management/

# Run with HTTPS
docker run -d --name pt-management \
  -p 5000:5000 -p 5443:5443 \
  -v ./ssl/server.crt:/etc/ssl/certs/server.crt:ro \
  -v ./ssl/server.key:/etc/ssl/private/server.key:ro \
  -e ENABLE_HTTPS=true \
  -e SSL_CERT_PATH=/etc/ssl/certs/server.crt \
  -e SSL_KEY_PATH=/etc/ssl/private/server.key \
  pt-management:latest
```

### Verify SSL Configuration

```bash
# Check certificate details
openssl x509 -in ssl/server.crt -text -noout

# Verify key matches certificate
openssl x509 -noout -modulus -in ssl/server.crt | md5sum
openssl rsa -noout -modulus -in ssl/server.key | md5sum
```

---

## Security Notes

⚠️ **Self-signed certificates (from `generate-ssl-cert.sh`)** are suitable for:
- Development environments
- Internal testing
- Lab environments

✓ **Production deployments** should use:
- Certificates from a trusted Certificate Authority (Let's Encrypt, DigiCert, etc.)
- Proper DNS records pointing to your server
- HSTS headers configured in nginx
- Regular certificate renewal (automated via certbot or similar)

---

## Related Files

- **Main script**: `deploy-full.sh`
- **Management tool**: `manage-https.sh`
- **Dockerfile**: `pt-management/Dockerfile`
- **Startup script**: `pt-management/start.sh` (embedded in Dockerfile)
- **Configuration**: `.env`
- **SSL Cert Generator**: `generate-ssl-cert.sh`

---

For questions or issues, check container logs:

```bash
docker logs pt-management
docker logs pt-nginx1
```
