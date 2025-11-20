#!/bin/bash
# Automatic GPU Setup and Configuration Script
# Detects NVIDIA GPU and installs/configures Docker GPU support

set -e

echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║          Automatic GPU Detection & Setup Script                    ║"
echo "║                   For Docker GPU Support                           ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
NC='\033[0m' # No Color

# Helper functions
print_status() {
    echo -e "${BLUE}[*]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# ============================================================================
echo -e "\n${BLUE}═══ Phase 1: GPU Detection ═══${NC}\n"

# Check for NVIDIA GPU
print_status "Checking for NVIDIA GPU..."

if command -v nvidia-smi &> /dev/null; then
    print_success "nvidia-smi found"
    
    GPU_INFO=$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null | head -1)
    print_success "GPU Details: $GPU_INFO"
    GPU_DETECTED=true
else
    print_error "nvidia-smi not found"
    print_warning "NVIDIA drivers may not be installed"
    GPU_DETECTED=false
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 2: Docker Installation Check ═══${NC}\n"

# Check if Docker is installed
print_status "Checking Docker installation..."

if command -v docker &> /dev/null; then
    print_success "Docker is installed"
    DOCKER_VERSION=$(docker --version)
    print_success "Docker version: $DOCKER_VERSION"
else
    print_error "Docker is not installed"
    exit 1
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 3: Docker GPU Runtime Check ═══${NC}\n"

# Test if Docker can access GPU
print_status "Testing Docker GPU runtime access..."

if docker run --rm --gpus all ubuntu:22.04 which nvidia-smi &>/dev/null 2>&1; then
    print_success "Docker GPU runtime is already configured!"
    print_success "No further setup needed"
    GPU_RUNTIME_WORKS=true
else
    print_warning "Docker GPU runtime not working"
    GPU_RUNTIME_WORKS=false
    
    echo ""
    print_status "Attempting to fix Docker GPU runtime configuration..."
    echo ""
    
    # ========================================================================
    echo -e "\n${BLUE}═══ Phase 4: Install nvidia-container-runtime ═══${NC}\n"
    
    # Detect OS
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        OS=$ID
    else
        print_error "Cannot detect OS"
        exit 1
    fi
    
    print_status "Detected OS: $OS"
    
    case $OS in
        ubuntu|debian)
            print_status "Installing nvidia-container-runtime for Ubuntu/Debian..."
            
            # Add NVIDIA Docker GPG key
            if ! command -v curl &> /dev/null; then
                print_warning "curl not found, attempting apt install..."
                sudo apt-get update
                sudo apt-get install -y curl
            fi
            
            print_status "Adding NVIDIA Docker GPG key..."
            curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg 2>/dev/null || {
                print_warning "Could not add GPG key from URL, trying alternative..."
            }
            
            print_status "Adding NVIDIA Docker repository..."
            curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
                sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list 2>/dev/null || {
                print_warning "Could not add repository from URL"
            }
            
            print_status "Updating package lists..."
            sudo apt-get update 2>/dev/null || print_warning "apt-get update had issues"
            
            print_status "Installing nvidia-container-toolkit..."
            sudo apt-get install -y nvidia-container-toolkit 2>/dev/null || {
                print_error "Failed to install nvidia-container-toolkit via apt"
                print_status "Trying alternative installation method..."
            }
            ;;
            
        fedora|rhel|centos)
            print_status "Installing nvidia-container-runtime for Fedora/RHEL/CentOS..."
            
            print_status "Adding NVIDIA Docker repository..."
            distribution=$(. /etc/os-release;echo $ID$VERSION_ID) && \
            curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.repo | \
            sudo tee /etc/yum.repos.d/nvidia-container-toolkit.repo 2>/dev/null || print_warning "Could not add repo"
            
            print_status "Installing nvidia-container-toolkit..."
            sudo yum install -y nvidia-container-toolkit 2>/dev/null || {
                print_error "Failed to install via yum"
            }
            ;;
            
        arch|manjaro)
            print_status "Installing nvidia-container-runtime for Arch/Manjaro..."
            
            print_status "Installing from AUR..."
            if command -v yay &> /dev/null; then
                yay -S nvidia-container-toolkit --noconfirm 2>/dev/null || print_warning "yay install may have issues"
            elif command -v pamac &> /dev/null; then
                pamac install nvidia-container-toolkit -U -y 2>/dev/null || print_warning "pamac install may have issues"
            else
                print_warning "No AUR helper found. Please install nvidia-container-toolkit manually"
            fi
            ;;
            
        *)
            print_warning "Unsupported OS: $OS"
            print_status "Please install nvidia-container-toolkit manually"
            print_status "Visit: https://github.com/NVIDIA/nvidia-docker"
            ;;
    esac
    
    # ========================================================================
    echo -e "\n${BLUE}═══ Phase 5: Configure Docker Daemon ═══${NC}\n"
    
    # Check if nvidia-container-runtime is now available
    if command -v nvidia-container-runtime &> /dev/null; then
        print_success "nvidia-container-runtime is now installed"
        
        # Update Docker daemon.json
        print_status "Configuring Docker daemon to use NVIDIA runtime..."
        
        # Backup original
        if [ -f /etc/docker/daemon.json ]; then
            print_status "Backing up original daemon.json to daemon.json.bak"
            sudo cp /etc/docker/daemon.json /etc/docker/daemon.json.bak
        fi
        
        # Create new daemon.json with NVIDIA runtime
        print_status "Creating new Docker daemon configuration..."
        
        # Use a temporary file for the new config
        TMP_DAEMON=$(mktemp)
        
        if [ -f /etc/docker/daemon.json ]; then
            # Merge with existing config
            jq '. + {
                "runtimes": {
                    "nvidia": {
                        "path": "nvidia-container-runtime",
                        "runtimeArgs": []
                    }
                }
            }' /etc/docker/daemon.json > "$TMP_DAEMON" 2>/dev/null || {
                # If jq fails, create new config
                cat > "$TMP_DAEMON" <<'EOF'
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
EOF
            }
        else
            # Create new config
            cat > "$TMP_DAEMON" <<'EOF'
{
    "runtimes": {
        "nvidia": {
            "path": "nvidia-container-runtime",
            "runtimeArgs": []
        }
    }
}
EOF
        fi
        
        # Copy to destination
        sudo cp "$TMP_DAEMON" /etc/docker/daemon.json
        rm "$TMP_DAEMON"
        
        print_success "Docker daemon.json updated with NVIDIA runtime"
        
        # Restart Docker daemon
        print_status "Restarting Docker daemon..."
        sudo systemctl restart docker 2>/dev/null || {
            print_warning "Could not restart docker via systemctl"
            print_status "Trying alternative restart method..."
            sudo service docker restart 2>/dev/null || print_warning "Docker restart may have issues"
        }
        
        print_success "Docker daemon restarted"
        
        # Test GPU access
        sleep 3
        print_status "Testing Docker GPU access..."
        
        if docker run --rm --gpus all ubuntu:22.04 which nvidia-smi &>/dev/null 2>&1; then
            print_success "✓ Docker GPU runtime is now working!"
            GPU_RUNTIME_WORKS=true
        else
            print_warning "Docker GPU access test still failing"
            print_status "Trying with 'docker run --gpus all'..."
            
            # Try alternative GPU access method
            if docker run --rm --gpus=all ubuntu:22.04 which nvidia-smi &>/dev/null 2>&1; then
                print_success "✓ Docker GPU access works with '--gpus=all' format"
                GPU_RUNTIME_WORKS=true
            else
                print_warning "Docker GPU access not working yet"
                print_warning "This may require a system restart"
                GPU_RUNTIME_WORKS=false
            fi
        fi
    else
        print_error "nvidia-container-runtime installation failed"
        print_status "Please install it manually: https://github.com/NVIDIA/nvidia-docker"
    fi
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 6: Summary & Recommendations ═══${NC}\n"

if [ "$GPU_DETECTED" = true ] && [ "$GPU_RUNTIME_WORKS" = true ]; then
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}✓ GPU SETUP COMPLETE AND VERIFIED!${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    print_success "NVIDIA GPU detected and Docker GPU runtime configured"
    print_success "You can now deploy PacketTracer with GPU support"
    echo ""
    print_status "Next step: Run deployment script"
    echo "  cd PacketTracerWeb/"
    echo "  bash deploy.sh"
    echo ""
    
elif [ "$GPU_DETECTED" = true ] && [ "$GPU_RUNTIME_WORKS" = false ]; then
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}⚠ GPU DETECTED BUT DOCKER ACCESS NOT YET WORKING${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    print_warning "NVIDIA GPU is detected on the system"
    print_warning "Docker GPU runtime configuration needs attention"
    echo ""
    print_status "Recommendations:"
    echo "  1. Restart your system: sudo reboot"
    echo "  2. Or check Docker socket: sudo usermod -aG docker \$USER"
    echo "  3. Or manually install nvidia-docker: https://github.com/NVIDIA/nvidia-docker"
    echo ""
    
elif [ "$GPU_DETECTED" = false ]; then
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${YELLOW}⚠ NO GPU DETECTED${NC}"
    echo -e "${YELLOW}═══════════════════════════════════════════════════════════${NC}"
    echo ""
    print_warning "NVIDIA GPU not detected on this system"
    print_warning "PacketTracer will run with CPU-only software rendering"
    echo ""
    print_status "This is acceptable for:"
    echo "  - Educational environments"
    echo "  - Testing and development"
    echo "  - 2D network topology diagrams"
    print_warning "But 3D rendering will be limited or unavailable"
    echo ""
    print_status "To add GPU support:"
    echo "  1. Install NVIDIA GPU hardware"
    echo "  2. Install NVIDIA drivers: https://www.nvidia.com/Download/driverDetails.aspx"
    echo "  3. Run this script again"
    echo ""
fi

# ============================================================================
echo -e "\n${BLUE}═══ Phase 7: Docker Version Check ═══${NC}\n"

print_status "Verifying Docker configuration..."
docker version --format 'Client: {{.Client.Version}}, Server: {{.Server.Version}}'

# Check daemon.json
if [ -f /etc/docker/daemon.json ]; then
    echo ""
    print_status "Current Docker daemon configuration:"
    cat /etc/docker/daemon.json | jq . 2>/dev/null || cat /etc/docker/daemon.json
fi

echo ""
print_status "Setup script completed"
echo ""

# Exit with appropriate code
if [ "$GPU_RUNTIME_WORKS" = true ]; then
    exit 0
else
    exit 1
fi
