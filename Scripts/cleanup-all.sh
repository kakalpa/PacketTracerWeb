#!/bin/bash

##############################################################################
# PacketTracer Scoped Docker Cleanup Script
# Safely removes containers, volumes, and networks belonging to PacketTracerWeb
# CAUTION: Scoped exclusively to PacketTracerWeb resources.
##############################################################################

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    PacketTracer Deployment - Scoped Project Cleanup   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# Confirmation prompt
echo -e "${YELLOW}⚠️  WARNING: This will permanently remove PacketTracer resources:${NC}"
echo "  • Containers: guacamole-mariadb, pt-guacd, pt-guacamole, pt-nginx1, pt-management, pt-certbot, ptvnc*"
echo "  • Volumes:    mariadb_data, dbdump, pt_opt"
echo "  • Networks:   ptnet, pt-stack, pt-vncnet"
echo "  • Images:     pt-nginx, pt-management, pt-certbot, ptvnc"
echo ""
echo -e "${GREEN}✓ Other containers, images, and volumes on your host will NOT be touched.${NC}"
echo ""

read -p "Are you sure you want to clean up PacketTracer resources? Type 'yes' to continue: " confirm

if [ "$confirm" != "yes" ]; then
    echo -e "${YELLOW}❌ Cleanup cancelled.${NC}"
    exit 0
fi

echo ""
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}Starting scoped cleanup process...${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""

# Helper to find project containers
get_project_containers() {
    docker ps -a --format "{{.Names}}" | grep -E '^(guacamole-mariadb|pt-guacd|pt-guacamole|pt-nginx1|pt-management|pt-certbot|ptvnc.*)$' || true
}

# Step 1: Stop project containers
echo -e "${BLUE}[1/5] Stopping PacketTracer containers...${NC}"
RUNNING_CONTAINERS=$(docker ps --format "{{.Names}}" | grep -E '^(guacamole-mariadb|pt-guacd|pt-guacamole|pt-nginx1|pt-management|pt-certbot|ptvnc.*)$' || true)
if [ -n "$RUNNING_CONTAINERS" ]; then
    echo "$RUNNING_CONTAINERS" | xargs -r docker stop 2>/dev/null || true
    echo -e "${GREEN}✓ Stopped running PacketTracer containers${NC}"
else
    echo -e "${YELLOW}ℹ️  No running PacketTracer containers to stop${NC}"
fi
echo ""

# Step 2: Remove project containers
echo -e "${BLUE}[2/5] Removing PacketTracer containers...${NC}"
ALL_PROJECT_CONTAINERS=$(get_project_containers)
if [ -n "$ALL_PROJECT_CONTAINERS" ]; then
    echo "$ALL_PROJECT_CONTAINERS" | xargs -r docker rm -f 2>/dev/null || true
    echo -e "${GREEN}✓ Removed PacketTracer containers${NC}"
else
    echo -e "${YELLOW}ℹ️  No PacketTracer containers to remove${NC}"
fi
echo ""

# Step 3: Remove project networks
echo -e "${BLUE}[3/5] Removing PacketTracer networks...${NC}"
docker network rm ptnet pt-stack pt-vncnet 2>/dev/null || true
echo -e "${GREEN}✓ Cleaned up project networks (ptnet, pt-stack, pt-vncnet)${NC}"
echo ""

# Step 4: Remove project volumes
echo -e "${BLUE}[4/5] Removing PacketTracer volumes (mariadb_data, dbdump, pt_opt)...${NC}"
PROJECT_VOLUMES=$(docker volume ls --format "{{.Name}}" | grep -E '^(mariadb_data|dbdump|pt_opt|ptweb-vnc_.*)$' || true)
if [ -n "$PROJECT_VOLUMES" ]; then
    echo "$PROJECT_VOLUMES" | xargs -r docker volume rm 2>/dev/null || true
    echo -e "${GREEN}✓ Removed PacketTracer volumes${NC}"
else
    echo -e "${YELLOW}ℹ️  No PacketTracer volumes to remove${NC}"
fi
echo ""

# Step 5: Remove project images
echo -e "${BLUE}[5/5] Removing PacketTracer application images...${NC}"
PROJECT_IMAGES=$(docker images --format "{{.Repository}}:{{.Tag}}" | grep -E '^(pt-nginx|pt-management|pt-certbot|ptvnc)' || true)
if [ -n "$PROJECT_IMAGES" ]; then
    echo "$PROJECT_IMAGES" | xargs -r docker rmi 2>/dev/null || true
    echo -e "${GREEN}✓ Removed PacketTracer application images${NC}"
else
    echo -e "${YELLOW}ℹ️  No PacketTracer application images to remove${NC}"
fi
echo ""

# Final status
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Scoped cleanup finished successfully!${NC}"
echo -e "${BLUE}═══════════════════════════════════════════════════════${NC}"
echo ""
echo -e "${GREEN}✓ System is ready for a fresh deployment!${NC}"
echo ""
echo "Next steps:"
echo "  1. Copy your PacketTracer .deb file to the repo root (if not already present)"
echo "  2. Run: bash deploy-full.sh"
echo ""
