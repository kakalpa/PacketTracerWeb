FROM python:3.11-slim

WORKDIR /app

# Force rebuild - Timestamp: 1730975000
# Install system dependencies including Docker CLI and sudo
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    sudo \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends \
    docker-ce-cli \
    && rm -rf /var/lib/apt/lists*

# Allow root user to run docker commands via sudo without password
RUN echo "root ALL=(ALL) NOPASSWD: /usr/bin/docker" >> /etc/sudoers.d/docker

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Explicitly copy templates to ensure they're included
COPY templates/ /app/templates/

# Create necessary directories
RUN mkdir -p logs static/js static/css templates /app/ssl

# Expose ports (HTTP and HTTPS)
EXPOSE 5000 5443

# Copy startup script
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Health check uses HTTP endpoint (no SSL overhead)
HEALTHCHECK --interval=10s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Run startup script
CMD ["/app/start.sh"]
