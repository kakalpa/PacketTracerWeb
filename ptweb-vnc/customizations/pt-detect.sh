#!/bin/bash
# Helper to detect Packet Tracer binary and create consistent symlink
set -euo pipefail

PT_DIR="/opt/pt"
PT_LINK="/opt/pt/packettracer"

if [ -x "$PT_LINK" ]; then
    echo "Packet Tracer symlink already exists: $PT_LINK"
    exit 0
fi

if [ -d "$PT_DIR" ]; then
    # Look for common binary names
    for name in packettracer PacketTracer PacketTracer7 PacketTracer8; do
        if [ -x "$PT_DIR/$name" ]; then
            ln -sfn "$PT_DIR/$name" "$PT_LINK"
            echo "Created symlink $PT_LINK -> $PT_DIR/$name"
            exit 0
        fi
    done
fi

echo "No Packet Tracer binary found in $PT_DIR"
exit 1
