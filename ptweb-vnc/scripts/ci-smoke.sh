#!/usr/bin/env bash
set -euo pipefail

# This script is a local fallback for the GitHub Actions smoke step.
# It builds the Docker image and runs a container to verify that /opt/pt/packettracer exists.

docker build -t ptvnc .

docker run --rm --entrypoint /bin/bash ptvnc -lc '\
  set -e; \
  candidates=(/opt/pt/packettracer /opt/pt/bin/PacketTracer /opt/pt/bin/PacketTracer7 /opt/pt/bin/packettracer); \
  for p in "${candidates[@]}"; do \
    if [ -x "$p" ]; then echo "OK: found Packet Tracer binary at $p"; exit 0; fi; \
  done; \
  echo "Missing Packet Tracer binary in /opt/pt"; ls -la /opt/pt || true; exit 2'
