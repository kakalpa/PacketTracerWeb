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
  log_progress "Contents of /opt/pt: $(ls -la /opt/pt/ | head -20)"
  
  # Find the actual binary (could be at different locations in different versions)
  binary_path=""
  if [ -x /opt/pt/bin/PacketTracer ]; then
    binary_path="/opt/pt/bin/PacketTracer"
    log_progress "Found binary at: $binary_path"
  elif [ -x /opt/pt/PacketTracer ]; then
    binary_path="/opt/pt/PacketTracer"
    log_progress "Found binary at: $binary_path"
  else
    # Search for any executable named PacketTracer
    binary_path=$(find /opt/pt -name "PacketTracer" -type f -executable 2>/dev/null | head -n1 || true)
    if [ -n "$binary_path" ]; then
      log_progress "Found binary at: $binary_path"
    else
      log_progress "Searching for executable files in /opt/pt..."
      find /opt/pt -type f -executable 2>/dev/null | head -10 | while read -r file; do
        log_progress "  Found executable: $file"
      done
    fi
  fi
  
  # Create wrapper script if binary was found
  if [ -n "$binary_path" ] && [ -x "$binary_path" ]; then
    if [ ! -e /opt/pt/packettracer ]; then
      log_progress "Creating wrapper script for PacketTracer binary..."
      cat > /opt/pt/packettracer << WRAPPER
#!/bin/bash
export LD_LIBRARY_PATH=/opt/pt/bin:\$LD_LIBRARY_PATH
export QT_QPA_PLATFORM_PLUGIN_PATH=/opt/pt/bin
exec $binary_path "\$@"
WRAPPER
      chmod +x /opt/pt/packettracer
      log_progress "Created wrapper script /opt/pt/packettracer"
    fi
  fi
fi

# Check for binary with multiple fallback methods
binary_found=false
if [ -x /opt/pt/packettracer ]; then
  log_progress "✓ Wrapper script found at /opt/pt/packettracer"
  binary_found=true
elif [ -x /opt/pt/bin/PacketTracer ]; then
  log_progress "✓ Binary found at /opt/pt/bin/PacketTracer"
  binary_found=true
elif [ -x /opt/pt/PacketTracer ]; then
  log_progress "✓ Binary found at /opt/pt/PacketTracer"
  binary_found=true
else
  # Last resort: search for any executable
  found_binary=$(find /opt/pt -name "PacketTracer" -type f -executable 2>/dev/null | head -n1 || true)
  if [ -n "$found_binary" ]; then
    log_progress "✓ Binary found at: $found_binary"
    binary_found=true
  fi
fi

if [ "$binary_found" = true ]; then
  log_progress "✓ SUCCESS: PacketTracer binary ready"
  log_progress "Installation complete!"
  exit 0
else
  log_progress "✗ ERROR: PacketTracer binary not found at expected locations"
  log_progress "Listing /opt/pt contents:"
  ls -la /opt/pt 2>&1 | head -30 | while read -r line; do
    log_progress "  $line"
  done
  exit 1
fi
