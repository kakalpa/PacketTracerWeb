# Security Guide for PacketTracerWeb

This document provides security best practices and hardening steps for deploying PacketTracerWeb to production environments, especially on public internet.

## 🔒 Security Overview

### Default Credentials ⚠️ **CHANGE THESE IMMEDIATELY**

| Service | Default User | Default Password | Risk |
|---------|--------------|------------------|------|
| Guacamole Web UI | `ptadmin` | `IlovePT` | CRITICAL |
| MariaDB | `ptdbuser` | `ptdbpass` | CRITICAL |
| VNC Server | N/A | `Cisco123` | HIGH |
| MariaDB Root | `root` | random | MEDIUM |

---

## 🚀 Production Deployment Checklist

### Phase 1: Before First Deployment

- [ ] Generate strong random passwords (minimum 16 characters)
- [ ] Prepare HTTPS/TLS certificates
- [ ] Plan firewall rules
- [ ] Set up centralized logging
- [ ] Review and sign off on security policy

### Phase 2: Initial Setup

- [ ] Use `secure-setup.sh` to generate random credentials
- [ ] Store credentials securely (vault, encrypted file)
- [ ] Deploy with HTTPS enabled
- [ ] Configure network isolation
- [ ] Enable all security features in nginx

### Phase 3: Post-Deployment

- [ ] Change all default credentials
- [ ] Run `test-deployment.sh` to verify setup
- [ ] Set up monitoring and alerts
- [ ] Rotate logs daily
- [ ] Document access procedures

---

## 🔐 Step 1: Generate Secure Credentials

### Option A: Automatic (Recommended)

```bash
bash secure-setup.sh
```

This script:
- Generates cryptographically strong passwords
- Creates `.env.secure` with all credentials
- Updates docker-compose.yml and deploy.sh
- Shows you credentials ONE TIME (save securely!)

### Option B: Manual

Set these environment variables before running deploy.sh:

```bash
export DB_ROOT_PASSWORD="$(openssl rand -base64 32)"
export DB_USER_PASSWORD="$(openssl rand -base64 32)"
export VNC_PASSWORD="$(openssl rand -base64 24)"
export GUACAMOLE_PASSWORD="$(openssl rand -base64 16)"

# Then run:
bash deploy.sh
```

---

## 🔒 Step 2: Enable HTTPS/TLS

### With Let's Encrypt (Production Recommended)

```bash
# 1. Install certbot
sudo apt-get install certbot python3-certbot-nginx

# 2. Get certificate for your domain
sudo certbot certonly --standalone -d your-domain.com

# 3. Copy cert to project
mkdir -p ptweb-vnc/certs
sudo cp /etc/letsencrypt/live/your-domain.com/fullchain.pem ptweb-vnc/certs/
sudo cp /etc/letsencrypt/live/your-domain.com/privkey.pem ptweb-vnc/certs/
sudo chown $USER:$USER ptweb-vnc/certs/*

# 4. Redeploy with HTTPS
bash deploy.sh
```

### With Self-Signed Certificate (Testing)

```bash
mkdir -p ptweb-vnc/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ptweb-vnc/certs/privkey.pem \
  -out ptweb-vnc/certs/fullchain.pem \
  -subj "/C=US/ST=State/L=City/O=Org/CN=your-domain.com"

# Then deploy
bash deploy.sh
```

---

## 🚫 Step 3: Network Isolation

### Restrict Access by IP

Edit `ptweb-vnc/pt-nginx/conf/ptweb.conf`:

```nginx
# Allow only specific IP addresses
geo $ip_whitelist {
    default 0;
    192.168.1.0/24 1;      # Your office network
    203.0.113.5/32 1;      # Your VPN IP
}

server {
    listen 443 ssl http2;
    
    # Rate limiting
    limit_req_zone $binary_remote_addr zone=guac_limit:10m rate=10r/s;
    limit_req zone=guac_limit burst=20 nodelay;
    
    # Only allow whitelisted IPs
    if ($ip_whitelist = 0) {
        return 403;
    }
    
    # ... rest of config
}
```

### Restrict Database Access

MariaDB should only be accessible from containers:

```yaml
# docker-compose.yml
mariadb:
  ports: []  # Don't expose port 3306
  networks:
    - internal-network
  
networks:
  internal-network:
    internal: true  # Not accessible from host
```

---

## 🔑 Step 4: Strong Authentication

### Configure Guacamole Authentication

The database includes a default user. To strengthen:

1. **Connect to Guacamole admin panel:**
   - `http://your-ip/`
   - Login: `ptadmin` / `IlovePT` (your new password)

2. **Change default password:**
   - Settings → Users → ptadmin → Edit
   - Change password to strong value

3. **Add VPN/SSO (Optional):**
   - Guacamole supports LDAP, Kerberos, OIDC
   - See: https://guacamole.apache.org/doc/gug/

### Enable Rate Limiting (see nginx config above)

---

## 📊 Step 5: Enable Logging & Monitoring

### Centralized Logging

```bash
# Create logging directory
mkdir -p logs
chmod 777 logs

# All containers will log here
docker logs pt-guacamole >> logs/guacamole.log
docker logs pt-nginx1 >> logs/nginx.log
docker logs guacamole-mariadb >> logs/mariadb.log
```

### Monitor Security Events

```bash
# Watch for failed logins
tail -f logs/guacamole.log | grep -i "authentication\|failed\|error"

# Watch for access attempts
tail -f logs/nginx.log | grep "403\|401\|error"

# Monitor database
docker exec guacamole-mariadb tail -f /var/log/mysql/error.log
```

### Set Up Alerts

Use your infrastructure monitoring tool:
- **Prometheus**: Scrape Nginx metrics
- **ELK Stack**: Centralize logs
- **CloudWatch**: If using AWS
- **Datadog**: If using managed monitoring

---

## 🔄 Step 6: Regular Maintenance

### Weekly
- [ ] Review access logs for suspicious activity
- [ ] Check disk space (containers use `/shared`)
- [ ] Verify all services healthy: `bash test-deployment.sh`

### Monthly
- [ ] Rotate credentials (especially VNC password)
- [ ] Update Docker images: `docker pull guacamole/guacamole`
- [ ] Review security patches for dependencies
- [ ] Audit user accounts (create/remove as needed)

### Quarterly
- [ ] Full security audit
- [ ] Penetration testing (if critical system)
- [ ] Review and update firewall rules
- [ ] Rotate TLS certificates (90 days before expiry)

### Annually
- [ ] Update Cisco Packet Tracer to latest version
- [ ] Review and update security policy
- [ ] Backup and test disaster recovery

---

## 🚨 Security Hardening Commands

### Lock Down File Permissions

```bash
# Restrict .env files
chmod 600 .env.secure

# Restrict certs
chmod 600 ptweb-vnc/certs/*

# Restrict logs
chmod 700 logs/
chmod 600 logs/*
```

### Disable Unnecessary Services

```bash
# If you don't need direct database access:
# Remove from docker-compose.yml or use:
docker network disconnect pt_default mariadb

# If you don't need downloads from web:
# Comment out /downloads location in nginx config
```

### Enable Docker Security Best Practices

```bash
# Run containers as non-root (already done in Dockerfile)
# Verify:
docker inspect ptvnc1 | grep -i "user"

# Enable AppArmor/SELinux on host (for Linux)
sudo apparmor_parser -r /etc/apparmor.d/docker-default

# Use read-only filesystem where possible
# (modify docker-compose.yml as needed)
```

---

## 🛡️ Firewall Configuration

### UFW (Ubuntu)

```bash
# Default: deny all, allow only what's needed
sudo ufw default deny incoming
sudo ufw default allow outgoing

# Allow SSH (keep access to server!)
sudo ufw allow 22/tcp

# Allow HTTP/HTTPS
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Deny everything else
sudo ufw enable
```

### iptables (Advanced)

```bash
# Allow only from VPN/trusted IP
sudo iptables -A INPUT -s 203.0.113.5 -p tcp --dport 80 -j ACCEPT
sudo iptables -A INPUT -s 203.0.113.5 -p tcp --dport 443 -j ACCEPT
sudo iptables -A INPUT -p tcp --dport 80 -j DROP
sudo iptables -A INPUT -p tcp --dport 443 -j DROP
```

---

## 📋 Incident Response

### If Password is Compromised

```bash
# 1. Immediately change Guacamole password
docker exec pt-guacamole bash -c \
  'mysql -u ptdbuser -p"$MYSQL_PASSWORD" guacamole_db -e \
   "UPDATE guacamole_user SET password_hash=... WHERE username=\"ptadmin\";"'

# 2. Check audit logs
tail -1000 logs/guacamole.log | grep -i "ptadmin"

# 3. Review active sessions
docker exec pt-guacamole bash -c \
  'mysql -u ptdbuser -p"$MYSQL_PASSWORD" guacamole_db -e \
   "SELECT * FROM guacamole_user_history LIMIT 20;"'

# 4. Regenerate VNC passwords
bash remove-instance.sh
bash add-instance.sh  # Creates new instances with new VNC passwords
```

### If Database is Breached

```bash
# 1. Stop all containers
docker-compose -f ptweb-vnc/docker-compose.yml stop

# 2. Remove compromised database
docker volume rm guacamole_db_data

# 3. Restart with clean database
docker-compose -f ptweb-vnc/docker-compose.yml up -d
```

### If Server is Compromised

```bash
# 1. Isolate from network immediately
sudo ifconfig eth0 down  # Or use your interface name

# 2. Contact your security team

# 3. Full audit needed:
sudo aide --init  # Generate AIDE database
sudo aide --check  # Check for file changes
docker images  # Check for modified images
docker volume inspect pt_opt  # Check for tampering
```

---

## 🔗 Security References

- [OWASP Top 10](https://owasp.org/www-project-top-ten/)
- [CIS Docker Benchmark](https://www.cisecurity.org/benchmark/docker/)
- [Guacamole Security](https://guacamole.apache.org/doc/gug/#security)
- [Nginx Security](https://nginx.org/en/docs/security_advisory.html)
- [MariaDB Security](https://mariadb.com/kb/en/security/)

---

## ⚠️ Known Limitations

1. **VNC is unencrypted by design** - It's proxied through HTTPS/Guacamole, but raw VNC is not encrypted
2. **File sharing is world-readable** - `/shared` permissions should be restricted by firewall
3. **Default timeouts may be too long** - Adjust session timeout in Guacamole settings
4. **No multi-factor authentication (MFA)** - Only available through LDAP/SSO integration

---

## 📞 Support

For security issues:
- Create a **private security advisory** on GitHub
- DO NOT open public issues for security vulnerabilities
- Contact: [provide your contact email]

---

**Last Updated:** October 31, 2025  
**Status:** Production Ready ✅
