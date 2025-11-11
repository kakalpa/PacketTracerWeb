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

# Extract and install manually to bypass preinst agreement prompt
# The preinst script tries to show an EULA dialog which fails in containers
log_progress "Extracting PacketTracer .deb (this may take 2-3 minutes)..."
mkdir -p /tmp/pt_extract
if ! dpkg-deb -x "$deb" /tmp/pt_extract; then
  log_progress "ERROR: Failed to extract .deb file"
  exit 1
fi
log_progress "✓ Extraction completed"

# Copy files to final locations
log_progress "Installing files to /opt/pt..."
if [ -d /tmp/pt_extract/opt/pt ]; then
  cp -r /tmp/pt_extract/opt/pt/* /opt/pt/ 2>/dev/null || true
  log_progress "✓ Files copied to /opt/pt"
else
  log_progress "ERROR: /opt/pt not found in extracted .deb"
  exit 1
fi

# Install system files from /usr (symlinks, desktop files, mime types)
if [ -d /tmp/pt_extract/usr ]; then
  log_progress "Installing system files..."
  cp -r /tmp/pt_extract/usr/* /usr/ 2>/dev/null || true
  log_progress "✓ System files installed"
fi

log_progress "Installation completed"
log_progress "Contents of /opt/pt: $(find /opt/pt -type f | wc -l) files"

# The 9.0.0+ .deb already contains both binaries - detect which is available
log_progress "Checking for PacketTracer binaries..."

# Version 9.0.0+ installs wrapper at /opt/pt/packettracer and binary at /opt/pt/bin/PacketTracer
if [ -x /opt/pt/packettracer ]; then
  log_progress "✓ Found wrapper script: /opt/pt/packettracer"
fi

if [ -x /opt/pt/bin/PacketTracer ]; then
  log_progress "✓ Found binary: /opt/pt/bin/PacketTracer"
fi

# Final validation - check for PacketTracer wrapper script
log_progress "Verifying PacketTracer installation..."

if [ -x /opt/pt/packettracer ] || [ -x /opt/pt/bin/PacketTracer ]; then
  log_progress "✓ SUCCESS: PacketTracer installed and ready!"
  log_progress "✓ Wrapper: $([ -x /opt/pt/packettracer ] && echo 'YES' || echo 'NO')"
  log_progress "✓ Binary: $([ -x /opt/pt/bin/PacketTracer ] && echo 'YES' || echo 'NO')"
  log_progress "Installation complete!"
  exit 0
else
  log_progress "✗ FATAL ERROR: PacketTracer installation failed"
  log_progress "Expected executables not found:"
  log_progress "  - /opt/pt/packettracer (wrapper)"
  log_progress "  - /opt/pt/bin/PacketTracer (binary)"
  log_progress "Actual /opt/pt contents:"
  if [ -d /opt/pt ]; then
    ls -lhA /opt/pt 2>&1 | head -20 | while read -r line; do
      log_progress "  $line"
    done
    if [ -d /opt/pt/bin ]; then
      log_progress "Contents of /opt/pt/bin:"
      ls -lhA /opt/pt/bin 2>&1 | head -15 | while read -r line; do
        log_progress "    $line"
      done
    fi
  else
    log_progress "  /opt/pt directory does not exist!"
  fi
  log_progress "dpkg install log (last 50 lines):"
  tail -50 /tmp/dpkg_install.log 2>/dev/null | while read -r line; do
    log_progress "  $line"
  done
  exit 1
fi
