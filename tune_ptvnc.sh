#!/bin/bash
# Increase memory and cpu for running ptvnc containers. Adjust values as needed.
# Usage: bash tune_ptvnc.sh [mem] [cpus]
mem=${1:-2G}
cpus=${2:-1}

for c in $(docker ps -a --format '{{.Names}}' | grep '^ptvnc' || true); do
  echo "Updating $c -> memory=$mem cpus=$cpus"
  # Update both memory and memoryswap to avoid conflicts
  # memoryswap should be 2x the memory limit to allow swap
  docker update --memory "$mem" --memory-swap "$mem" --cpus "$cpus" "$c" || true
done

echo "Done"
