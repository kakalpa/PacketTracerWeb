#!/usr/bin/env bash
set -euo pipefail

# Idempotent runtime installer for Packet Tracer
# Behavior:
# - If /var/lib/pt_installed exists and matches the candidate deb checksum, skip install
# - Accepts PT_DEB_PATH (explicit deb path) or searches common locations for a .deb
# - Accepts PT_DEB_SHA1 to verify the installer before running
# - Uses /pt-install.sh if available, otherwise falls back to dpkg -i + apt-get -f install

MARKER_FILE=/var/lib/pt_installed
PT_DEB_PATH=${PT_DEB_PATH:-}
PT_DEB_SHA1=${PT_DEB_SHA1:-}
VERBOSE=${VERBOSE:-1}

log() { if [ "$VERBOSE" -gt 0 ]; then echo "$@"; fi }

# If /opt/pt contains the PacketTracer binary or a marker file, treat as installed
if [ -x "/opt/pt/packettracer" ] || [ -f "/opt/pt/.pt_installed" ]; then
  log "Packet Tracer appears already installed under /opt/pt (binary or marker present); skipping runtime install."
  # Still write global marker if missing
  if [ ! -f "$MARKER_FILE" ]; then
    echo "installed:existing" > "$MARKER_FILE" || true
  fi
  exit 0
fi

# If marker exists and matches requested checksum, skip
if [ -f "$MARKER_FILE" ]; then
  if [ -n "$PT_DEB_SHA1" ]; then
    marker_sha="$(awk -F: '/^sha1:/ {print $2}' "$MARKER_FILE" || true)"
    if [ "$marker_sha" = "$PT_DEB_SHA1" ]; then
      log "Marker matches requested SHA1; skipping install."
      exit 0
    fi
  else
    log "Marker file present; skipping install."
    exit 0
  fi
fi

find_candidate() {
  # If PT_DEB_PATH is set and exists, use it
  if [ -n "$PT_DEB_PATH" ] && [ -f "$PT_DEB_PATH" ]; then
    echo "$PT_DEB_PATH"
    return 0
  fi

  # search common locations
  for p in /PacketTracer*.deb /*PacketTracer*.deb /CiscoPacketTracer*.deb /install/*.deb /opt/install/*.deb; do
    for f in $p; do
      if [ -f "$f" ]; then
        echo "$f"
        return 0
      fi
    done
  done
  return 1
}

debfile=""
if debfile="$(find_candidate 2>/dev/null || true)"; then
  log "Found Packet Tracer installer: $debfile"
else
  log "No Packet Tracer .deb found at startup; skipping install."
  exit 0
fi

# verify checksum if provided
if [ -n "$PT_DEB_SHA1" ]; then
  if command -v sha1sum >/dev/null 2>&1; then
    actual_sha1="$(sha1sum "$debfile" | awk '{print $1}')"
    if [ "$actual_sha1" != "$PT_DEB_SHA1" ]; then
      echo "Checksum mismatch: expected $PT_DEB_SHA1 but got $actual_sha1" >&2
      exit 1
    fi
    log "Checksum verified: $actual_sha1"
  else
    echo "sha1sum not available to verify PT_DEB_SHA1" >&2
    exit 1
  fi
fi

# Run the packaged installer if available
export DEBIAN_FRONTEND=noninteractive
install_success=false
if [ -x /pt-install.sh ]; then
  log "Running /pt-install.sh (non-interactive)..."
  # Ensure installer sees the .deb at a predictable path
  cp -f "$debfile" /PacketTracer.deb || true
  if /pt-install.sh; then
    install_success=true
  fi
else
  log "/pt-install.sh not found; attempting dpkg -i + apt-get -f install"
  if dpkg -i "$debfile" && apt-get -y -f install && dpkg --configure -a; then
    install_success=true
  fi
fi

# marker: record installed filename and sha1 (if available)
installed_sha=""
if command -v sha1sum >/dev/null 2>&1; then
  installed_sha="$(sha1sum "$debfile" | awk '{print $1}')" || true
fi
echo "file:$(basename "$debfile")" > "$MARKER_FILE" || true
if [ -n "$installed_sha" ]; then
  echo "sha1:$installed_sha" >> "$MARKER_FILE" || true
fi

# Also write a marker inside the shared /opt/pt volume so installer-service
# patterns and subsequent containers mounting /opt/pt can detect installation.
if [ -d "/opt/pt" ] || mkdir -p /opt/pt 2>/dev/null; then
  marker_opt=/opt/pt/.pt_installed
  echo "file:$(basename "$debfile")" > "$marker_opt" || true
  if [ -n "$installed_sha" ]; then
    echo "sha1:$installed_sha" >> "$marker_opt" || true
  fi
fi

if [ "$install_success" = true ] && { [ -x "/opt/pt/packettracer" ] || [ -d "/opt/pt" ]; }; then
  log "Packet Tracer installed successfully."
  exit 0
else
  echo "Packet Tracer install failed or binary not found under /opt/pt" >&2
  # Remove markers on failure
  rm -f "$MARKER_FILE" /opt/pt/.pt_installed || true
  exit 1
fi
