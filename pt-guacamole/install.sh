#!/bin/bash
set -e

# --- Configurable variables ---
swapsize="8G"
swapfile="/swap.img"
dbuser="ptdbuser"
dbpass="ptdbpass"
dbname="guacamole_db"
numofPT=10
PTfile="Packet_Tracer822_amd64_signed.deb"
PTfilechecksum="35bd819fcb0e2ed1df3582387d599e4a9c6bf2c9"
nginxport=80
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

# --- Functions ---
function startnotice() {
    echo -e "\e[1mThis script installs Docker + Cisco Packet Tracer stack.\033[0m"
    echo "TCP port ${nginxport} will be opened publicly."
    read -p "Type YES to continue: " ans
    [[ "$ans" == "YES" ]] || exit 1
}

function checkPTfile() {
    echo "Checking Packet Tracer installer..."
    if [[ ! -f "${project_dir}/${PTfile}" ]]; then
        echo "❌ Missing Packet Tracer installer file: ${PTfile}"
        echo "Please place it in: ${project_dir}"
        exit 1
    fi
    echo "${PTfilechecksum}  ${project_dir}/${PTfile}" | sha1sum -c || {
        echo "❌ Checksum mismatch! Wrong file or corrupted download."
        exit 1
    }
}

function setup_system() {
    echo "Installing Docker and dependencies..."
    apt update -y
    apt install -y docker.io docker-compose sharutils
    systemctl enable docker
    systemctl start docker
}

function createswap() {
    if [[ ! -f "$swapfile" ]]; then
        echo "Creating swap file (${swapsize})..."
        fallocate -l "$swapsize" "$swapfile"
        chmod 600 "$swapfile"
        mkswap "$swapfile"
        swapon "$swapfile"
        echo "$swapfile none swap sw 0 0" >> /etc/fstab
    else
        echo "Swap file already exists, skipping..."
    fi
}

function build_docker() {
    echo "Building Packet Tracer Docker image..."
    cp "${project_dir}/${PTfile}" "${project_dir}/ptweb-vnc/" || {
        echo "⚠️ Could not copy Packet Tracer file to ptweb-vnc/. Check permissions."
        exit 1
    }
    cd "${project_dir}/ptweb-vnc"
    docker build -t ptvnc .
    cd "${project_dir}"
}

function start_stack() {
    echo "Starting Docker Compose stack..."
    docker-compose up -d
}

# --- Run sequence ---
clear
startnotice
checkPTfile
setup_system
createswap
build_docker
start_stack

echo
echo "✅ All services running successfully."
echo "Access Guacamole via: http://<server-ip>:${nginxport}"

