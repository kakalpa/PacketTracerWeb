#!/usr/bin/env bash
set -euo pipefail

# Find PacketTracer .deb with common patterns. Match any filename that contains 'PacketTracer'
deb=$(ls /*PacketTracer*.deb /PacketTracer* /PacketTracer_* /PacketTracer-*_amd64.deb 2>/dev/null | head -n1 || true)
if [ -z "$deb" ]; then
  deb=$(ls /PacketTracer*_amd64.deb 2>/dev/null | head -n1 || true)
fi

if [ -z "$deb" ]; then
  echo "No PacketTracer .deb found"
  exit 0
fi

echo "Installing PacketTracer from: $deb"
# Make the install non-interactive and pre-accept the Cisco EULA by piping 'yes'
export DEBIAN_FRONTEND=noninteractive
# Preseed debconf to accept EULA (use package name 'packettracer' with template keys)
echo "packettracer PacketTracer_822_amd64/accept-eula boolean true" | debconf-set-selections || true

# Install using dpkg then fix deps with apt-get to avoid interactive prompts
dpkg -i "$deb" || true
apt-get -y -f install || true
dpkg --configure -a || true
