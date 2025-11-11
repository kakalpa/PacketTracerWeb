#!/bin/bash

##############################################################################
# Complete Cleanup + Redeploy Script
# Cleans up all Docker resources and immediately starts fresh deployment
##############################################################################

set -e

BLUE='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    PacketTracer - Full Cleanup & Redeploy             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Get directory
WORKDIR="$(cd "$(dirname "$0")" && pwd)"
cd "$WORKDIR"

# Confirmation
echo -e "${YELLOW}⚠️  This will:${NC}"
echo "  1. Delete ALL containers, images, volumes, and cache"
echo "  2. Immediately start fresh deployment"
echo ""

read -p "Continue? Type 'yes': " confirm
if [ "$confirm" != "yes" ]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Running cleanup...${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Stop all containers
echo "Stopping containers..."
docker stop $(docker ps -q) 2>/dev/null || true
sleep 2

# Remove all containers
echo "Removing containers..."
docker rm $(docker ps -aq) 2>/dev/null || true

# Remove all images
echo "Removing images..."
docker rmi $(docker images -q) 2>/dev/null || true

# Remove all volumes
echo "Removing volumes..."
docker volume rm $(docker volume ls -q) 2>/dev/null || true

# Prune system
echo "Pruning Docker system..."
docker system prune -f --volumes 2>/dev/null || true

echo ""
echo -e "${GREEN}✓ Cleanup complete!${NC}"
echo ""

# Verify .deb file exists
if [ ! -f "CiscoPacketTracer.deb" ]; then
    echo -e "${YELLOW}⚠️  WARNING: CiscoPacketTracer.deb not found in $(pwd)${NC}"
    echo "Please copy the .deb file to this directory before running deployment."
    echo ""
    exit 1
fi

echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}Starting fresh deployment...${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Run deployment
bash deploy-full.sh
