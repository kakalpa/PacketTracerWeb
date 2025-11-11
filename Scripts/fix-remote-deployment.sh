#!/bin/bash

##############################################################################
# Remote Server - Fix PacketTracer Installation
# Use this on your remote server to diagnose and fix installation issues
##############################################################################

set -e

BLUE='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║    PacketTracer Installation Fix Guide                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${YELLOW}Current Status:${NC}"
echo "✗ PacketTracer binary not found after extraction"
echo "✓ Files copied to /opt/pt successfully"
echo ""

echo -e "${YELLOW}This guide will:${NC}"
echo "1. Pull latest installation script from repository"
echo "2. Stop and remove failed containers"
echo "3. Redeploy with improved binary detection"
echo ""

# Step 1: Update repository
echo -e "${BLUE}Step 1: Updating repository to latest code...${NC}"
cd ~/PacketTracerWeb
git fetch origin
git reset --hard origin/dev
echo -e "${GREEN}✓ Repository updated${NC}"
echo ""

# Step 2: Stop containers
echo -e "${BLUE}Step 2: Stopping ptvnc containers...${NC}"
docker stop ptvnc1 ptvnc2 2>/dev/null || true
echo -e "${GREEN}✓ Containers stopped${NC}"
echo ""

# Step 3: Remove containers
echo -e "${BLUE}Step 3: Removing failed containers...${NC}"
docker rm ptvnc1 ptvnc2 2>/dev/null || true
echo -e "${GREEN}✓ Containers removed${NC}"
echo ""

# Step 4: Clear the shared volume to start fresh
echo -e "${BLUE}Step 4: Clearing shared PacketTracer volume...${NC}"
docker volume rm pt_opt 2>/dev/null || true
echo -e "${GREEN}✓ Volume cleared${NC}"
echo ""

# Step 5: Rebuild Docker image with new script
echo -e "${BLUE}Step 5: Rebuilding Docker image with improved installation script...${NC}"
cd ~/PacketTracerWeb/ptweb-vnc
docker build -t ptvnc . --progress=plain
echo -e "${GREEN}✓ Image rebuilt${NC}"
echo ""

# Step 6: Redeploy
echo -e "${BLUE}Step 6: Starting fresh deployment...${NC}"
cd ~/PacketTracerWeb
bash deploy-full.sh

echo ""
echo -e "${GREEN}✓ Deployment complete!${NC}"
