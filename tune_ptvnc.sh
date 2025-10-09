#!/bin/bash
# Increase memory and cpu for running ptvnc containers. Adjust values as needed.
# Usage: sudo ./tune_ptvnc.sh [mem] [cpus]
mem=${1:-2G}
cpus=${2:-1}

for c in $(sudo docker ps -a --format '{{.Names}}' | grep '^ptvnc' || true); do
  echo "Updating $c -> memory=$mem cpus=$cpus"
  sudo docker update --memory "$mem" --cpus "$cpus" "$c" || true
done

echo "Done"
