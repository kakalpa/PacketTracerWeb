FROM python:3.11-slim

WORKDIR /app

# Force rebuild - Timestamp: 1730975000
# Install system dependencies including Docker CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    openssl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null \
    && apt-get update && apt-get install -y --no-install-recommends \
    docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Explicitly copy templates to ensure they're included
COPY templates/ /app/templates/

# Create necessary directories
RUN mkdir -p logs static/js static/css templates /etc/ssl/certs /etc/ssl/private

# Ensure entrypoint and start-https scripts are executable
RUN chmod +x /app/entrypoint.sh /app/start-https.sh 2>/dev/null || true

# Expose port
EXPOSE 5000

# Run entrypoint script supporting SSL/HTTP on port 5000
ENTRYPOINT ["/app/entrypoint.sh"]
