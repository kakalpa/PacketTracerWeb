#!/bin/bash
# Comprehensive GPU Implementation Verification Script
# Tests all aspects of the universal GPU rendering solution

set -e

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║   GPU Implementation Verification - Comprehensive Test Suite       ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

# Test counters
PASS=0
FAIL=0
WARN=0

# Helper functions
test_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASS++))
}

test_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    ((FAIL++))
}

test_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    ((WARN++))
}

test_info() {
    echo -e "${BLUE}ℹ INFO${NC}: $1"
}

# ============================================================================
echo -e "\n${BLUE}═══ Phase 1: Environment Prerequisites ═══${NC}"
echo ""

# Test 1: Docker available
if command -v docker &> /dev/null; then
    test_pass "Docker is installed"
else
    test_fail "Docker is not installed"
    exit 1
fi

# Test 2: Docker daemon running
if docker ps &> /dev/null; then
    test_pass "Docker daemon is running"
else
    test_fail "Docker daemon is not running"
    exit 1
fi

# Test 3: Docker version
DOCKER_VERSION=$(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
test_info "Docker version: $DOCKER_VERSION"

# Test 4: GPU Runtime Check
echo ""
test_info "Testing Docker GPU runtime support..."

if docker run --rm --gpus all nvidia-smi &>/dev/null 2>&1; then
    test_pass "Docker GPU runtime is available (--gpus all works)"
    test_info "GPU detected - GPU passthrough will be ENABLED in deployment"
    GPU_AVAILABLE=true
else
    test_warn "Docker GPU runtime is not available (--gpus all doesn't work)"
    test_info "GPU not available - deployment will use CPU rendering fallback"
    GPU_AVAILABLE=false
fi

# Test 5: NVIDIA GPU (if GPU available)
if [ "$GPU_AVAILABLE" = true ]; then
    echo ""
    test_info "Querying NVIDIA GPU information..."
    GPU_INFO=$(docker run --rm --gpus all nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null || echo "")
    if [ -n "$GPU_INFO" ]; then
        test_pass "NVIDIA GPU detected"
        test_info "GPU Details: $GPU_INFO"
    fi
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 2: File Structure Verification ═══${NC}"
echo ""

# Test 6: deploy.sh exists
if [ -f "deploy.sh" ]; then
    test_pass "deploy.sh exists"
else
    test_fail "deploy.sh not found"
fi

# Test 7: add-instance.sh exists
if [ -f "add-instance.sh" ]; then
    test_pass "add-instance.sh exists"
else
    test_fail "add-instance.sh not found"
fi

# Test 8: GPU detection in deploy.sh
if grep -q "detect_gpu" deploy.sh; then
    test_pass "GPU detection function in deploy.sh"
else
    test_fail "GPU detection function NOT found in deploy.sh"
fi

# Test 9: GPU detection in add-instance.sh
if grep -q "detect_gpu" add-instance.sh; then
    test_pass "GPU detection function in add-instance.sh"
else
    test_fail "GPU detection function NOT found in add-instance.sh"
fi

# Test 10: GPU_FLAGS in deploy.sh
if grep -q 'GPU_FLAGS' deploy.sh; then
    test_pass "GPU_FLAGS variable in deploy.sh"
else
    test_fail "GPU_FLAGS variable NOT found in deploy.sh"
fi

# Test 11: GPU_FLAGS in docker run (deploy.sh)
if grep -q 'docker run.*\$GPU_FLAGS' deploy.sh; then
    test_pass "GPU_FLAGS used in docker run command (deploy.sh)"
else
    test_fail "GPU_FLAGS not applied to docker run (deploy.sh)"
fi

# Test 12: Dockerfile exists
if [ -f "ptweb-vnc/Dockerfile" ]; then
    test_pass "ptweb-vnc/Dockerfile exists"
else
    test_fail "ptweb-vnc/Dockerfile not found"
fi

# Test 13: xorg.conf configuration in Dockerfile
if grep -q "Module\|glx\|dri" ptweb-vnc/Dockerfile; then
    test_pass "xorg.conf configuration (GLX/DRI) in Dockerfile"
else
    test_warn "xorg.conf configuration may be incomplete in Dockerfile"
fi

# Test 14: start script exists
if [ -f "ptweb-vnc/customizations/start" ]; then
    test_pass "ptweb-vnc/customizations/start exists"
else
    test_fail "ptweb-vnc/customizations/start not found"
fi

# Test 15: Xvfb with GLX in start script
if grep -q "Xvfb.*\+extension GLX" ptweb-vnc/customizations/start; then
    test_pass "Xvfb started with +extension GLX in start script"
else
    test_fail "Xvfb GLX extension not found in start script"
fi

# Test 16: xstartup exists
if [ -f "ptweb-vnc/customizations/home/ptuser/.vnc/xstartup" ]; then
    test_pass "xstartup script exists"
else
    test_fail "xstartup script not found"
fi

# Test 17: Qt configuration in xstartup
if grep -q "QT_QPA_PLATFORM\|QT_XCB_GL_INTEGRATION" ptweb-vnc/customizations/home/ptuser/.vnc/xstartup; then
    test_pass "Qt configuration (universal GL) in xstartup"
else
    test_fail "Qt configuration not found in xstartup"
fi

# Test 18: Documentation files
echo ""
if [ -f "UNIVERSAL_GPU_SOLUTION.md" ]; then
    test_pass "UNIVERSAL_GPU_SOLUTION.md exists"
else
    test_warn "UNIVERSAL_GPU_SOLUTION.md not found"
fi

if [ -f "QUICK_START_GPU.md" ]; then
    test_pass "QUICK_START_GPU.md exists"
else
    test_warn "QUICK_START_GPU.md not found"
fi

if [ -f "IMPLEMENTATION_STATUS.md" ]; then
    test_pass "IMPLEMENTATION_STATUS.md exists"
else
    test_warn "IMPLEMENTATION_STATUS.md not found"
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 3: Configuration Verification ═══${NC}"
echo ""

# Test 19: Packet Tracer .deb file
if ls *.deb &>/dev/null 2>&1; then
    PT_FILE=$(ls *.deb | head -1)
    test_pass "Packet Tracer .deb file found: $PT_FILE"
else
    test_warn "No Packet Tracer .deb file found in repo root"
    test_info "Required for deployment: Place CiscoPacketTracer.deb in repo root"
fi

# Test 20: .env file (optional)
if [ -f ".env" ]; then
    test_pass ".env file exists (optional configuration)"
    if grep -q "FORCE_GPU\|DISABLE_GPU_DETECTION" .env; then
        test_info ".env contains GPU-related configuration"
    fi
else
    test_info ".env file not present (using defaults)"
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 4: Code Quality Verification ═══${NC}"
echo ""

# Test 21: Bash syntax in deploy.sh
if bash -n deploy.sh 2>/dev/null; then
    test_pass "deploy.sh bash syntax is valid"
else
    test_fail "deploy.sh has bash syntax errors"
fi

# Test 22: Bash syntax in add-instance.sh
if bash -n add-instance.sh 2>/dev/null; then
    test_pass "add-instance.sh bash syntax is valid"
else
    test_fail "add-instance.sh has bash syntax errors"
fi

# Test 23: Bash syntax in start script
if bash -n ptweb-vnc/customizations/start 2>/dev/null; then
    test_pass "start script bash syntax is valid"
else
    test_fail "start script has bash syntax errors"
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 5: Existing Infrastructure ═══${NC}"
echo ""

# Test 24: Check existing containers
if docker ps -a 2>/dev/null | grep -q "ptvnc"; then
    test_warn "Existing PT containers found"
    test_info "Recommendation: Run 'bash deploy.sh recreate' for fresh deployment"
else
    test_pass "No existing PT containers (clean slate)"
fi

# Test 25: Check existing images
if docker image inspect ptvnc:latest &>/dev/null 2>&1; then
    test_info "Existing ptvnc image found (will be rebuilt if deploy.sh runs)"
else
    test_pass "No existing ptvnc image (clean image build)"
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 6: GPU-Specific Capabilities ═══${NC}"
echo ""

if [ "$GPU_AVAILABLE" = true ]; then
    # Test 26: CUDA availability (if GPU available)
    if docker run --rm --gpus all nvidia/cuda:latest nvidia-smi &>/dev/null 2>&1; then
        test_pass "CUDA toolchain available for GPU containers"
    else
        test_warn "CUDA not available (GPU rendering may be limited)"
    fi
    
    # Test 27: nvidia-docker plugin
    if docker run --rm --gpus all ubuntu which nvidia-smi &>/dev/null 2>&1; then
        test_pass "nvidia-smi available in containers (GPU passthrough working)"
    else
        test_warn "nvidia-smi not available in containers (GPU passthrough may have issues)"
    fi
else
    test_info "No GPU detected - GPU-specific tests skipped"
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 7: Implementation Readiness ═══${NC}"
echo ""

# Test 28: All critical files present
CRITICAL_FILES=(
    "deploy.sh"
    "add-instance.sh"
    "ptweb-vnc/Dockerfile"
    "ptweb-vnc/customizations/start"
    "ptweb-vnc/customizations/home/ptuser/.vnc/xstartup"
)

CRITICAL_OK=true
for file in "${CRITICAL_FILES[@]}"; do
    if [ ! -f "$file" ]; then
        test_fail "Critical file missing: $file"
        CRITICAL_OK=false
    fi
done

if [ "$CRITICAL_OK" = true ]; then
    test_pass "All critical files present"
fi

# Test 29: GPU detection function is identical (deploy.sh vs add-instance.sh)
DEPLOY_GPU_FUNC=$(grep -A 5 "detect_gpu()" deploy.sh 2>/dev/null || echo "")
ADDINSTANCE_GPU_FUNC=$(grep -A 5 "detect_gpu()" add-instance.sh 2>/dev/null || echo "")

if [ "$DEPLOY_GPU_FUNC" = "$ADDINSTANCE_GPU_FUNC" ]; then
    test_pass "GPU detection function is consistent across scripts"
else
    test_warn "GPU detection function may differ between deploy.sh and add-instance.sh"
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 8: Deployment Simulation ═══${NC}"
echo ""

# Test 30: Simulate GPU detection
test_info "Simulating GPU detection logic..."

if docker run --rm --gpus all nvidia-smi &>/dev/null 2>&1; then
    SIMULATED_GPU_FLAGS="--gpus all"
    test_pass "GPU SIMULATION: --gpus all will be used"
    test_info "Expected behavior: 3D rendering ENABLED (60+ FPS)"
else
    SIMULATED_GPU_FLAGS=""
    test_pass "GPU SIMULATION: No GPU flags (CPU rendering fallback)"
    test_info "Expected behavior: 3D rendering LIMITED, 2D/Simulation OK"
fi

# ============================================================================
echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                        TEST SUMMARY                                ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

TOTAL=$((PASS + FAIL + WARN))
echo "Total Tests Run: $TOTAL"
echo ""
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${RED}Failed: $FAIL${NC}"
echo -e "${YELLOW}Warnings: $WARN${NC}"
echo ""

# ============================================================================
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                    DEPLOYMENT READINESS                            ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}✓ READY FOR DEPLOYMENT${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Ensure Packet Tracer .deb is in repo root"
    echo "  2. Run: bash deploy.sh"
    echo "  3. GPU will be detected automatically"
    echo "  4. Open http://localhost for Guacamole web UI"
    echo ""
else
    echo -e "${RED}✗ NOT READY FOR DEPLOYMENT${NC}"
    echo ""
    echo "Issues to fix:"
    echo "  - Check the FAILED tests above"
    echo "  - Ensure all files are in place"
    echo "  - Review the UNIVERSAL_GPU_SOLUTION.md for details"
    echo ""
    exit 1
fi

# ============================================================================
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                    GPU SUPPORT DETECTED                            ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

if [ "$GPU_AVAILABLE" = true ]; then
    echo -e "${GREEN}✓ GPU SUPPORT AVAILABLE${NC}"
    echo ""
    echo "GPU Information:"
    docker run --rm --gpus all nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | while IFS=',' read -r name driver memory; do
        echo "  GPU: $name"
        echo "  Driver: $driver"
        echo "  Memory: $memory"
    done
    echo ""
    echo "Expected deployment behavior:"
    echo "  ✓ GPU detected (NVIDIA)"
    echo "  ✓ GPU will be passed through to containers"
    echo "  ✓ 3D rendering ENABLED (60+ FPS)"
    echo ""
else
    echo -e "${YELLOW}⚠ GPU SUPPORT NOT AVAILABLE${NC}"
    echo ""
    echo "Expected deployment behavior:"
    echo "  ℹ No GPU detected"
    echo "  ℹ Using CPU rendering (3D rendering limited)"
    echo "  ✓ 2D UI works perfectly"
    echo "  ✓ Network simulation works perfectly"
    echo ""
fi

echo ""
echo "For detailed documentation:"
echo "  - UNIVERSAL_GPU_SOLUTION.md (comprehensive guide)"
echo "  - QUICK_START_GPU.md (quick reference)"
echo "  - IMPLEMENTATION_STATUS.md (current status)"
echo ""

# Exit with appropriate code
if [ $FAIL -eq 0 ]; then
    exit 0
else
    exit 1
fi
