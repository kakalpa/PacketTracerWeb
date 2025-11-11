#!/bin/bash

##############################################################################
# Complete Docker Cleanup Script
# Removes all containers, images, volumes, and caches for a fresh deployment
# CAUTION: This is destructive and cannot be undone!
##############################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    PacketTracer Deployment - Complete Cleanup         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Confirmation prompt
echo -e "${YELLOW}⚠️  WARNING: This will permanently delete:${NC}"
echo "  • All running Docker containers"
echo "  • All Docker images"
echo "  • All Docker volumes (including PacketTracer installation)"
echo "  • All Docker build cache"
echo ""
echo -e "${YELLOW}This action CANNOT be undone!${NC}"
echo ""

read -p "Are you absolutely sure? Type 'yes' to continue: " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}❌ Cleanup cancelled.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Starting cleanup process...${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Stop all running containers
echo -e "${BLUE}[1/5] Stopping all running containers...${NC}"
if [ $(docker ps -q | wc -l) -gt 0 ]; then
    docker stop $(docker ps -q) 2>/dev/null || true
    echo -e "${GREEN}✓ Stopped all running containers${NC}"
else
    echo -e "${YELLOW}ℹ️  No running containers to stop${NC}"
fi
echo ""

# Step 2: Remove all containers
echo -e "${BLUE}[2/5] Removing all containers...${NC}"
if [ $(docker ps -aq | wc -l) -gt 0 ]; then
    docker rm $(docker ps -aq) 2>/dev/null || true
    echo -e "${GREEN}✓ Removed all containers${NC}"
else
    echo -e "${YELLOW}ℹ️  No containers to remove${NC}"
fi
echo ""

# Step 3: Remove all images
echo -e "${BLUE}[3/5] Removing all Docker images...${NC}"
if [ $(docker images -q | wc -l) -gt 0 ]; then
    docker rmi $(docker images -q) 2>/dev/null || true
    echo -e "${GREEN}✓ Removed all Docker images${NC}"
else
    echo -e "${YELLOW}ℹ️  No images to remove${NC}"
fi
echo ""

# Step 4: Remove all volumes (including pt_opt which has PacketTracer)
echo -e "${BLUE}[4/5] Removing all Docker volumes...${NC}"
if [ $(docker volume ls -q | wc -l) -gt 0 ]; then
    docker volume rm $(docker volume ls -q) 2>/dev/null || true
    echo -e "${GREEN}✓ Removed all Docker volumes${NC}"
else
    echo -e "${YELLOW}ℹ️  No volumes to remove${NC}"
fi
echo ""

# Step 5: Prune system (including build cache)
echo -e "${BLUE}[5/5] Pruning Docker system and build cache...${NC}"
docker system prune -f --volumes 2>/dev/null || true
echo -e "${GREEN}✓ Pruned Docker system${NC}"
echo ""

# Final status
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Complete cleanup finished successfully!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Show remaining resources
echo -e "${BLUE}Remaining Docker resources:${NC}"
echo -e "${YELLOW}Containers:${NC}"
docker ps -a --format "table {{.Names}}\t{{.Status}}" 2>/dev/null | head -5 || echo "  (none)"
echo ""
echo -e "${YELLOW}Images:${NC}"
docker images --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}" 2>/dev/null | head -5 || echo "  (none)"
echo ""
echo -e "${YELLOW}Volumes:${NC}"
docker volume ls --format "table {{.Name}}" 2>/dev/null | head -5 || echo "  (none)"
echo ""

echo -e "${GREEN}✓ System is now ready for a fresh deployment!${NC}"
echo ""
echo "Next steps:"
echo "  1. Copy your PacketTracer .deb file to the repo root"
echo "  2. Run: bash deploy-full.sh"
echo ""
