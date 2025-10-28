#!/usr/bin/env bash
set -euo pipefail

# Progress logging function with timestamps
log_progress() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] [pt-install] $1" >&2
}

# Find PacketTracer .deb with common patterns. Match any filename that contains 'PacketTracer'
log_progress "Searching for PacketTracer .deb file..."
deb=$(ls /*PacketTracer*.deb /PacketTracer* /PacketTracer_* /PacketTracer-*_amd64.deb 2>/dev/null | head -n1 || true)
if [ -z "$deb" ]; then
  deb=$(ls /PacketTracer*_amd64.deb 2>/dev/null | head -n1 || true)
fi

if [ -z "$deb" ]; then
  log_progress "No PacketTracer .deb found - skipping installation"
  exit 0
fi

log_progress "Found PacketTracer .deb: $deb"
log_progress "File size: $(du -h "$deb" | cut -f1)"
export DEBIAN_FRONTEND=noninteractive

# Preseed debconf to accept EULA (prevent interactive prompts)
log_progress "Presetting debconf for EULA acceptance..."
echo "packettracer PacketTracer_822_amd64/accept-eula boolean true" | debconf-set-selections || true

# Extract .deb manually using dpkg-deb to bypass problematic preinst script
# The preinst script tries to show an interactive EULA dialog which fails in containers
mkdir -p /tmp/pt_extract
log_progress "Extracting .deb contents (this may take 1-2 minutes)..."
if ! dpkg-deb -x "$deb" /tmp/pt_extract; then
  log_progress "ERROR: dpkg-deb extraction failed"
  exit 1
fi
log_progress "Extraction completed successfully"
log_progress "Extracted file count: $(find /tmp/pt_extract -type f | wc -l) files"

# Copy extracted files to their final locations
if [ -d /tmp/pt_extract/opt/pt ]; then
  # The volume is mounted at /opt/pt, so extract and copy contents directly
  log_progress "Copying files to /opt/pt (this may take 1-2 minutes)..."
  cp -r /tmp/pt_extract/opt/pt/* /opt/pt/ || true
  log_progress "Copy completed"
  
  # Create a wrapper script for the main binary to set library path and Qt plugins
  # Binary is at /opt/pt/bin/PacketTracer but start-session looks for /opt/pt/packettracer
  if [ -x /opt/pt/bin/PacketTracer ] && [ ! -e /opt/pt/packettracer ]; then
    log_progress "Creating wrapper script for PacketTracer binary..."
    cat > /opt/pt/packettracer << 'WRAPPER'
#!/bin/bash
export LD_LIBRARY_PATH=/opt/pt/bin:$LD_LIBRARY_PATH
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/pt/bin
exec /opt/pt/bin/PacketTracer "$@"
WRAPPER
    chmod +x /opt/pt/packettracer
    log_progress "Created wrapper script /opt/pt/packettracer"
  fi
fi

# If /opt/pt/packettracer exists, consider installation successful
if [ -x /opt/pt/packettracer ]; then
  log_progress "✓ SUCCESS: PacketTracer binary ready at /opt/pt/packettracer"
  log_progress "Installation complete!"
  exit 0
else
  log_progress "✗ ERROR: PacketTracer binary not found"
  exit 1
fi
