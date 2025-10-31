# GeoIP Filtering Guide for PacketTracerWeb

## Overview

GeoIP filtering allows you to restrict access to your PacketTracerWeb deployment based on geographic location (country). This is useful for:

- Restricting access to specific countries/regions
- Compliance with data sovereignty laws
- Preventing access from countries with trade embargoes
- Adding an extra layer of security

## Prerequisites

- Nginx with GeoIP2 module compiled in (standard in most distributions)
- MaxMind GeoIP2 database (free GeoLite2 or paid GeoIP2)
- Nginx configuration support

## Step 1: Check if GeoIP2 Module is Available

```bash
# Check if nginx has GeoIP2 module
nginx -V 2>&1 | grep -o 'with-http_geoip2_module\|geoip2'

# If not found, install nginx with GeoIP2 support:
# Ubuntu/Debian:
sudo apt-get install nginx-module-geoip2

# Or compile from source (see nginx docs)
```

## Step 2: Download MaxMind GeoIP2 Database

### Option A: Free GeoLite2 (Recommended for testing)

```bash
# Create account at: https://www.maxmind.com/en/account/login
# Sign up for free GeoLite2 download

# After creating account and generating license key:
mkdir -p ptweb-vnc/pt-nginx/conf/geoip-data
cd ptweb-vnc/pt-nginx/conf/geoip-data

# Download GeoLite2 City database
wget 'https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=YOUR_LICENSE_KEY&suffix=tar.gz' \
  -O GeoLite2-City.tar.gz

# Extract
tar -xzf GeoLite2-City.tar.gz
cp GeoLite2-City_*/GeoLite2-City.mmdb .

# Update weekly (recommended cron job)
# 0 3 * * * wget -O /tmp/geolite2.tar.gz 'https://download.maxmind.com/app/geoip_download?edition_id=GeoLite2-City&license_key=YOUR_LICENSE_KEY&suffix=tar.gz' && tar -xzf /tmp/geolite2.tar.gz -C /tmp && mv /tmp/GeoLite2-City_*/GeoLite2-City.mmdb ptweb-vnc/pt-nginx/conf/geoip-data/
```

### Option B: Paid GeoIP2 City Database

```bash
# Get subscription at: https://www.maxmind.com/en/geoip2-databases
# Download GeoIP2-City.tar.gz with your license key

mkdir -p ptweb-vnc/pt-nginx/conf/geoip-data
# Extract GeoIP2-City.mmdb to that directory
```

## Step 3: Configure Nginx with GeoIP2

### Enable GeoIP2 Module in Nginx

Create file: `ptweb-vnc/pt-nginx/conf/geoip2.conf`

```nginx
# GeoIP2 module configuration
load_module modules/ngx_http_geoip2_module.so;

geoip2 /etc/nginx/geoip-data/GeoLite2-City.mmdb {
    auto_reload 12h;
    $geoip2_data_country_code country iso_code;
}

map $geoip2_data_country_code $country_allowed {
    default 0;
    US 1;  # USA
    GB 1;  # UK
    DE 1;  # Germany
    CA 1;  # Canada
    AU 1;  # Australia
    # Add more countries as needed
}
```

### Update Main Nginx Configuration

In `ptweb-vnc/pt-nginx/conf/nginx.conf` (if it exists), add at the top:

```nginx
include geoip2.conf;
```

### Update Server Configuration

In `ptweb-vnc/pt-nginx/conf/ptweb-secure.conf`, uncomment GeoIP blocking:

```nginx
location ^~ /downloads/ {
    alias /shared/;
    
    # GeoIP Blocking
    if ($country_allowed = 0) {
        return 403;
    }
    
    # ... rest of config
}

location / {
    # Check country access
    if ($country_allowed = 0) {
        return 403;
    }
    
    # ... rest of config
}
```

## Step 4: Deploy with GeoIP Enabled

```bash
# 1. Create certificate directory for nginx
mkdir -p ptweb-vnc/pt-nginx/conf/geoip-data

# 2. Place GeoIP2 .mmdb file there
# (Copy GeoLite2-City.mmdb from Step 2)

# 3. Update docker-compose to mount the database
# Edit docker-compose.yml:
# volumes:
#   - ./ptweb-vnc/pt-nginx/conf/geoip-data:/etc/nginx/geoip-data:ro

# 4. Deploy
bash deploy.sh
```

## Step 5: Test GeoIP Filtering

```bash
# Test from different IP addresses
curl -H "CF-Connecting-IP: 1.1.1.1" http://localhost/

# Test with different country IPs
# Tor exit nodes can be used for testing

# Check Nginx logs
docker logs pt-nginx1 | grep 403
```

## Country Codes Reference

Common ISO 3166-1 alpha-2 country codes:

| Code | Country | Code | Country |
|------|---------|------|---------|
| US | United States | GB | United Kingdom |
| DE | Germany | FR | France |
| CA | Canada | AU | Australia |
| JP | Japan | CN | China |
| RU | Russia | IN | India |
| BR | Brazil | MX | Mexico |
| NZ | New Zealand | SG | Singapore |
| HK | Hong Kong | KR | South Korea |

Full list: https://en.wikipedia.org/wiki/ISO_3166-1_alpha-2

## Secure Setup Integration

### Using secure-setup.sh

```bash
# During setup, you'll be asked:
# "Enable GeoIP-based access restrictions? (y/n)"

# Answer 'y', then enter allowed countries:
# "Enter allowed country codes (comma-separated): US,GB,DE,CA"

# The script will:
# 1. Create geoip-allowed.conf
# 2. Generate configuration snippets
# 3. Set up proper file permissions
```

## Troubleshooting

### Nginx won't start with GeoIP module

```bash
# Check if module is compiled in
nginx -V | grep geoip2

# If not found, install:
sudo apt-get install libnginx-mod-http-geoip2

# Or use ngx_http_geoip_module (legacy, fewer features):
sudo apt-get install libnginx-mod-http-geoip
```

### GeoIP module not found error

```bash
# Error: "cannot load dynamic module" 
# Solution: Check module path

# Find installed modules:
ls /usr/share/nginx/modules/available/

# Or load manually in docker:
# Add to Dockerfile or docker-compose volumes
```

### Database file not found

```bash
# Check file permissions
ls -la ptweb-vnc/pt-nginx/conf/geoip-data/

# Must be readable by nginx (www-data in containers)
chmod 644 ptweb-vnc/pt-nginx/conf/geoip-data/GeoLite2-City.mmdb

# In docker-compose, ensure volume mount:
volumes:
  - ./ptweb-vnc/pt-nginx/conf/geoip-data:/etc/nginx/geoip-data:ro
```

### All requests blocked (403 Forbidden)

```bash
# Check if allowed countries are configured:
grep -A 10 "map \$country_allowed" ptweb-vnc/pt-nginx/conf/geoip-allowed.conf

# Test GeoIP lookup works:
docker exec pt-nginx1 geoiplookup 8.8.8.8

# Verify country codes are correct (2-letter ISO codes)
```

## Security Considerations

### Limitations

- **VPN Bypass**: Users can bypass GeoIP with VPN/proxies
- **ISP Geolocation**: Database may show ISP headquarters, not user location
- **Performance**: GeoIP lookup adds ~1-5ms per request
- **Database Updates**: Requires weekly/monthly updates for accuracy

### Best Practices

1. **Combine with other methods**:
   - Use GeoIP + IP whitelist
   - Use GeoIP + authentication
   - Use GeoIP + rate limiting

2. **Test regularly**:
   ```bash
   # Cron job to test GeoIP
   0 * * * * curl -s http://localhost/ > /dev/null || alert
   ```

3. **Monitor access**:
   ```bash
   # Check for blocked requests
   docker logs pt-nginx1 | grep "return 403"
   ```

4. **Keep database updated**:
   ```bash
   # Weekly update cron job
   0 3 * * 0 /usr/local/bin/update-geoip.sh
   ```

## Example: Allow US + UK + EU, Block Rest

```nginx
map $geoip2_data_country_code $country_allowed {
    default 0;
    
    # US + North America
    US 1;
    CA 1;
    
    # UK + EU
    GB 1;
    DE 1;
    FR 1;
    IT 1;
    ES 1;
    NL 1;
    BE 1;
    SE 1;
    DK 1;
    NO 1;
    FI 1;
    
    # Other approved
    AU 1;
    NZ 1;
}
```

## Advanced: Custom Geolocation Logic

```nginx
# Example: Allow US East Coast, Deny West Coast
# (Requires custom geoip module or commercial database)

map $geoip2_data_location_latitude $location_allowed {
    default 0;
    ~^(-?[0-4][0-9]\.|50\.)  1;  # Latitudes 0-50 (north)
}

# Combine conditions
server {
    location / {
        if ($country_allowed = 0) {
            return 403;
        }
        if ($location_allowed = 0) {
            return 403;
        }
    }
}
```

## Support & Resources

- MaxMind GeoIP2: https://www.maxmind.com/
- Nginx GeoIP2 Module: https://github.com/leev/ngx_http_geoip2_module
- ISO Country Codes: https://en.wikipedia.org/wiki/ISO_3166-1

---

**Last Updated:** October 31, 2025
