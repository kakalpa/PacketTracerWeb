#!/bin/bash


#Configurations
swapsize=4G
swapfile="/swap.img"
dbuser="ptdbuser"
dbpass="ptdbpass"
dbname="guacamole_db" 
# Default to a small number of Packet Tracer instances to avoid host resource exhaustion.
# Increase this if your host has sufficient RAM/CPU. For many hosts, 2-4 is safer.
numofPT=2
PTfile="CiscoPacketTracer822_amd64.deb"
# If you have a different PacketTracer installer (for example CiscoPacketTracer822_amd64.deb)
# the script will try to auto-detect it. Leave checksum empty to skip strict verification.
PTfilechecksum=""
nginxport=80
#1G memory + 4G swap can support about 10 concurrent PT user
#DO NOT change dbname

function startnotice() {
    echo -e "This script will install multiple packages and dockers on your system.\n"
    echo -e "\e[1mThe TCP port ${nginxport} will be opened to public after install!\033[0m\n"
    echo -e "This script was tested on a fresh installed Ubuntu 18.04 LTS (server) with 1G memory and 20G driver space.\n"
    echo -e "\e[1mDOWNLOADING, INSTALLING, OR USING THE CISCO PACKET TRACER SOFTWARE CONSTITUTES ACCEPTANCE OF THE CISCO END USER LICENSE AGREEMENT (“EULA”) AND THE SUPPLEMENTAL END USER LICENSE AGREEMENT FOR CISCO PACKET TRACER (“SEULA”).  IF YOU DO NOT AGREE TO ALL OF THE TERMS OF THE EULA AND SEULA, THEN CISCO SYSTEMS, INC. (“CISCO”) IS UNWILLING TO LICENSE THE SOFTWARE TO YOU AND YOU ARE NOT AUTHORIZED TO DOWNLOAD, INSTALL OR USE THE SOFTWARE.\033[0m\n"
    read -p "type ""YES"" to continue..." ans
    if [ "$ans" = "YES" ]; then
        return 0
    else exit 1
    fi
}

function checkPTfile(){
    # If the configured PTfile isn't present, try to auto-detect common filenames
    if [[ ! -f "$PTfile" ]]; then
        echo "Configured Packet Tracer file '$PTfile' not found, searching for any PacketTracer .deb in current folder..."
        candidate=$(ls -1 2>/dev/null | grep -E "PacketTracer|CiscoPacketTracer" | grep -E "\.deb$" | head -n1 || true)
        if [[ -n "$candidate" && -f "$candidate" ]]; then
            echo "Found candidate Packet Tracer installer: $candidate"
            PTfile="$candidate"
        else
            echo "Please copy a Packet Tracer installation file into the same folder with this script"
            echo "Get a copy of Packet Tracer by enrolling to a free Introduction to Packet Tracer course at https://www.netacad.com/courses/packet-tracer"
            exit 1
        fi
    fi

    # If a checksum is supplied, verify it. If it fails, warn and give user a chance to continue.
    if [[ -n "$PTfilechecksum" ]]; then
        echo "Verifying checksum for $PTfile (sha1)..."
        expected="${PTfilechecksum}  ${PTfile}"
        # create a temporary file with expected format for sha1sum -c
        tmpfile=$(mktemp)
        echo "$expected" > "$tmpfile"
        if ! sha1sum -c "$tmpfile" >/dev/null 2>&1; then
            echo "Warning: checksum verification failed for $PTfile"
            echo "Expected: $PTfilechecksum"
            echo "Actual:   $(sha1sum "$PTfile" | awk '{print $1}')"
            read -p "Checksum mismatch. Type YES to continue anyway, or anything else to abort: " anschk
            if [[ "$anschk" != "YES" ]]; then
                rm -f "$tmpfile"
                echo "Aborting due to checksum mismatch."
                exit 1
            fi
        fi
        rm -f "$tmpfile"
    else
        echo "No PTfilechecksum provided; skipping checksum verification for $PTfile"
    fi
}

# Ensure the script is run as root since it performs system changes
if [[ $EUID -ne 0 ]]; then
    echo "This installer must be run as root. Run with sudo or as root user."
    exit 1
fi

function aptup2date(){
    echo -e "\e[32mStep 1. Upgrade the packages...\e[0m"
    apt -y update
    apt -y upgrade
    installdocker
}

function installdocker(){
    echo -e "\e[32mStep 2. Install docker\e[0m"
    apt -y install docker.io
}

function createswap(){
    echo -e "\e[32mStep 3. Add swap space\e[0m"
    fallocate -l $swapsize $swapfile
    mkswap $swapfile
    swapon $swapfile
    fsbswapfile="${swapfile} none swap sw 0 0"
    echo ${fsbswapfile}| tee -a /etc/fstab
    echo 'vm.swappiness=10' | tee -a /etc/sysctl.conf
    echo 'vm.vfs_cache_pressure=50' | tee -a /etc/sysctl.conf
    echo 'GRUB_CMDLINE_LINUX="cgroup_enable=memory swapaccount=1"' | tee -a /etc/default/grub
    update-grub
}


function buildptvnc(){
    echo -e "\e[32mStep 5. Build Packet Tracer Docker container\e[0m"
    cd ptweb-vnc
    docker build . -t ptvnc
    cd ..
}

function pulldockerfiles(){
    echo -e "\e[32mStep 6. Pull required docker images\e[0m"
    docker pull mariadb
    docker pull guacamole/guacamole
    docker pull guacamole/guacd
    docker pull nginx
}

function startdb(){
    echo -e "\e[32mStep 7. Setup MariaDB\e[0m"
    docker run --name guacamole-mariadb --restart unless-stopped -v dbdump:/docker-entrypoint-initdb.d -e MYSQL_ROOT_HOST=% -e MYSQL_DATABASE=${dbname} -e MYSQL_USER=${dbuser} -e MYSQL_PASSWORD=${dbpass} -e MYSQL_RANDOM_ROOT_PASSWORD=1 -d mariadb:latest
    sleep 10
}

function startPT(){
    echo -e "\e[32mStep 8. Setup Packet Tracer containers, this will take a while, please wait..\e[0m"
    for ((i=1;i<=$numofPT;i++))
    do
        # If a container with the same name exists from a previous run, remove it first to avoid name conflict.
        docker rm -f ptvnc$i 2>/dev/null || true
        # Run with slightly higher memory and ulimits; avoid --kernel-memory which can cause constraints.
        # Mount the host PacketTracer .deb into the container at /PacketTracer.deb and
        # mount a named volume `pt_opt` at /opt/pt so the runtime installer can persist
        # installed files. Also pass PT_DEB_PATH and optional checksum to the container.
        docker run -d \
          --name ptvnc$i --restart unless-stopped \
          --cpus=0.1 -m 1G --oom-kill-disable --ulimit nproc=2048 --ulimit nofile=1024 \
          -v "$(pwd)/${PTfile}:/PacketTracer.deb:ro" \
          -v pt_opt:/opt/pt \
          -e PT_DEB_PATH=/PacketTracer.deb \
          -e PT_DEB_SHA1=${PTfilechecksum} \
          ptvnc
        sleep $i
    done
    sleep 1
}

function importdb(){
    echo -e "\e[32mStep 9. Import Guacamole DB\e[0m"
    sleep 20
    docker exec -i guacamole-mariadb mariadb -u${dbuser} -p${dbpass} <  ptweb-vnc/db-dump.sql
}

function startguacamole(){
    echo -e "\e[32mStep 10. Setup guacamole container\e[0m"
    linkstr=""
    for ((i=1;i<=$numofPT;i++))
    do
        linkstr="${linkstr} --link ptvnc$i:ptvnc$i"
    done
    docker run --name pt-guacd --restart always -d ${linkstr} guacamole/guacd
    sleep 20
    docker run --name pt-guacamole --restart always --link pt-guacd:guacd --link guacamole-mariadb:mysql -e MYSQL_DATABASE=${dbname} -e MYSQL_USER=${dbuser} -e MYSQL_PASSWORD=${dbpass} -d guacamole/guacamole
}

function startnginx(){
    echo -e "\e[32mStep 11. Setup nginx container\e[0m"
    docker run  --restart always --name pt-nginx1 --mount type=bind,source="$(pwd)"/ptweb-vnc/pt-nginx/www,target=/usr/share/nginx/html,readonly  --mount type=bind,source="$(pwd)"/ptweb-vnc/pt-nginx/conf,target=/etc/nginx/conf.d,readonly --link pt-guacamole:guacamole -p 80:$nginxport -d nginx
}



clear
checkPTfile
startnotice
aptup2date
createswap
buildptvnc
pulldockerfiles
startdb
startPT
importdb
startguacamole
startnginx

