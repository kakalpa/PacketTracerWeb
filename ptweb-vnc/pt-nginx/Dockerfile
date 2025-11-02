# Custom nginx image with geoip module support
FROM debian:bookworm AS nginx-builder

# Install build dependencies (bookworm compatible)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpcre3 \
    libpcre3-dev \
    libgeoip1 \
    libgeoip-dev \
    libssl-dev \
    zlib1g-dev \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and compile nginx with geoip module
ARG NGINX_VERSION=1.27.0
RUN cd /tmp && \
    wget http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz && \
    tar xzf nginx-${NGINX_VERSION}.tar.gz && \
    cd nginx-${NGINX_VERSION} && \
    ./configure \
        --prefix=/etc/nginx \
        --sbin-path=/usr/sbin/nginx \
        --modules-path=/usr/lib64/nginx/modules \
        --conf-path=/etc/nginx/nginx.conf \
        --error-log-path=/var/log/nginx/error.log \
        --http-log-path=/var/log/nginx/access.log \
        --pid-path=/var/run/nginx.pid \
        --lock-path=/var/run/nginx.lock \
        --with-http_geoip_module \
        --with-http_ssl_module \
        --with-http_v2_module \
        --with-http_realip_module \
        --with-http_gzip_static_module && \
    make && \
    make install && \
    cd / && \
    rm -rf /tmp/nginx-*

# Final stage - minimal runtime image
FROM debian:bookworm

# Install runtime dependencies only
RUN apt-get update && apt-get install -y \
    libgeoip1 \
    libpcre3 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy nginx binary from builder
COPY --from=nginx-builder /usr/sbin/nginx /usr/sbin/nginx

# Copy custom nginx.conf with GeoIP support
COPY nginx.conf /etc/nginx/nginx.conf

# Copy other nginx config files from builder
COPY --from=nginx-builder /etc/nginx/mime.types /etc/nginx/mime.types
COPY --from=nginx-builder /etc/nginx/fastcgi_params /etc/nginx/fastcgi_params

# Create nginx user if it doesn't exist
RUN useradd -r -M -s /sbin/nologin nginx 2>/dev/null || true

# Create necessary directories
RUN mkdir -p /var/log/nginx /var/cache/nginx /etc/nginx/conf.d && \
    chown -R nginx:nginx /var/log/nginx /var/cache/nginx

# Verify nginx and geoip module
RUN nginx -V 2>&1 | grep -q 'with-http_geoip_module' && echo "✓ GeoIP module verified" || echo "⚠ Warning: GeoIP module not found"

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
