#!/usr/bin/env bash
set -euo pipefail

# Find PacketTracer .deb with common patterns. Match any filename that contains 'PacketTracer'
deb=$(ls /*PacketTracer*.deb /PacketTracer* /PacketTracer_* /PacketTracer-*_amd64.deb 2>/dev/null | head -n1 || true)
if [ -z "$deb" ]; then
  deb=$(ls /PacketTracer*_amd64.deb 2>/dev/null | head -n1 || true)
fi

if [ -z "$deb" ]; then
  echo "No PacketTracer .deb found" >&2
  exit 0
fi

echo "Installing PacketTracer from: $deb" >&2
export DEBIAN_FRONTEND=noninteractive

# Preseed debconf to accept EULA (prevent interactive prompts)
echo "packettracer PacketTracer_822_amd64/accept-eula boolean true" | debconf-set-selections || true

# Extract .deb manually using dpkg-deb to bypass problematic preinst script
# The preinst script tries to show an interactive EULA dialog which fails in containers
mkdir -p /tmp/pt_extract
echo "[pt-install] Extracting .deb contents..." >&2
if ! dpkg-deb -x "$deb" /tmp/pt_extract; then
  echo "[pt-install] ERROR: dpkg-deb extraction failed" >&2
  exit 1
fi
echo "[pt-install] Extraction completed successfully" >&2

# Copy extracted files to their final locations
if [ -d /tmp/pt_extract/opt/pt ]; then
  # The volume is mounted at /opt/pt, so extract and copy contents directly
  echo "[pt-install] Copying files to /opt/pt..." >&2
  cp -r /tmp/pt_extract/opt/pt/* /opt/pt/ || true
  echo "[pt-install] Copy completed" >&2
  
  # Create a wrapper script for the main binary to set library path and Qt plugins
  # Binary is at /opt/pt/bin/PacketTracer but start-session looks for /opt/pt/packettracer
  if [ -x /opt/pt/bin/PacketTracer ] && [ ! -e /opt/pt/packettracer ]; then
    cat > /opt/pt/packettracer << 'WRAPPER'
#!/bin/bash
export LD_LIBRARY_PATH=/opt/pt/bin:$LD_LIBRARY_PATH
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/pt/bin
exec /opt/pt/bin/PacketTracer "$@"
WRAPPER
    chmod +x /opt/pt/packettracer
    echo "[pt-install] Created wrapper script /opt/pt/packettracer" >&2
  fi
fi

# If /opt/pt/packettracer exists, consider installation successful
if [ -x /opt/pt/packettracer ]; then
  echo "[pt-install] SUCCESS: PacketTracer binary ready at /opt/pt/packettracer" >&2
  exit 0
else
  echo "[pt-install] ERROR: PacketTracer binary not found" >&2
  exit 1
fi
