# System Assessment & Component Audit: PacketTracerWeb Baseline State

**Document Reference**: `docs/proposals/01_system_assessment.md`  
**Milestone**: M1 (System Assessment & Component Audit)  
**Author**: Worker Agent (`worker_m1`)  
**Target Architecture**: PacketTracerWeb Production Hardening Project  
**Date**: November 2026  
**Status**: COMPLETE / READY FOR SUB-ORCHESTRATOR REVIEW  

---

## 1. Executive Summary & Baseline State Architecture

### 1.1 Executive Summary
PacketTracerWeb is an educational and enterprise remote-learning platform designed to deliver isolated, browser-accessible instances of Cisco Packet Tracer over modern web standards without client-side software installation. The platform integrates X11 desktop virtualization (TurboVNC / VirtualGL), an HTML5 clientless remote desktop gateway (Apache Guacamole), an edge reverse proxy and TLS gateway (Nginx), and an orchestration/management API service (Flask / Gunicorn / MariaDB).

While the existing system demonstrates a functional proof-of-concept, this exhaustive technical audit reveals that **the baseline implementation is not production-ready**. Across all five core architectural components, the system exhibits critical vulnerabilities, architectural fragility, resource inefficiencies, and operational risks:
1. **Critical Security Vulnerabilities**:
   - The Flask management container runs as `root` with the host Docker socket (`/var/run/docker.sock`) mounted directly, combined with an unauthenticated container creation endpoint (`POST /api/containers`) and easily spoofable IP-based authentication bypasses. This allows trivial, unauthenticated root host compromise.
   - Administrative and database credentials (`ptdbpass`, `IlovePT`, `Cisco123`, `admin123`) are hardcoded across deployment scripts, source code, database dumps, and static web files (`bulk-user-api.php`), which are served publicly as plain text.
   - VNC authentication is explicitly disabled (`-securitytypes none`) on desktop containers, exposing RFB port 5901 without encryption or passwords.
   - Public directory indexing (`autoindex on`) on `/downloads/` exposes all user laboratory workspaces to unauthenticated external exfiltration.
2. **Operational Fragility & Data Loss Risks**:
   - The MariaDB database container utilizes an anonymous Docker volume for `/var/lib/mysql`, causing irreversible total data loss whenever the container is recreated or stack teardown occurs.
   - The instance deprovisioning workflow (`remove-instance.sh`) forcibly destroys and recreates `guacd`, `guacamole`, and `nginx`, disconnecting all active platform users.
   - Host cleanup scripts (`Scripts/cleanup-all.sh`) issue indiscriminate `docker rm` and `docker volume rm` commands that wipe the entire host Docker engine, destroying unrelated databases and containers.
   - Zero Docker `HEALTHCHECK` definitions exist across the repository; deployment sequencing depends on fragile 115-second hardcoded sleep timeouts.
3. **Resource Starvation & Interactive Degradation**:
   - Every desktop container runs concurrent duplicate X servers (`Xvfb :1` and `TurboVNC :2`), wasting over 200MB of RAM per container.
   - Default container shared memory (`/dev/shm`) is constrained to 64MB, causing Chromium/QtWebEngine rendering processes to crash during multi-window labs.
   - The absence of `proxy_buffering off;` in Nginx causes packet buffering of interactive Guacamole streams, introducing noticeable mouse latency and frame stutter.
   - Container process tables leak defunct zombie processes (`[AppRun] <defunct>`) due to the absence of a PID 1 subreaper.

This document establishes the empirical baseline audit required for Milestone 1, detailing **62 distinct technical findings** across all five components and all five operational domains.

---

### 1.2 Baseline State Architecture Topology

```
                       [ Client Browser (HTTPS) ]
                                   │
                                   ▼ (Port 443 / Port 5000)
                     [ Nginx Edge Gateway (pt-nginx) ]
                       ├── Custom compiled Nginx 1.27.0
                       ├── Legacy GeoIP1 (mailfud.org .dat) & Buggy Country Maps
                       ├── Flawed Trusted IPs Regex & Permissive TLS Ciphers
                       ├── Unauthenticated /downloads/ (autoindex on)
                       │
       ┌───────────────┴───────────────────────────────┬───────────────────────────────┐
       │ (Port 443 -> /guacamole/)                     │ (Port 443 -> /)               │ (Port 5000 -> /)
       ▼                                               ▼                               ▼
[ Apache Guacamole Webapp ]                     [ Direct Proxy ]             [ Flask Management API ]
  ├── Tomcat Container                            └── Bypasses index.html      ├── Python 3.11 / Gunicorn
  ├── MariaDB Backend (guacamole_db)                  and static assets        ├── Direct /var/run/docker.sock
  │   └── ANONYMOUS VOLUME (Data Loss Risk)                                    ├── Unauthenticated /api/containers
  │   └── Duplicate connections (NULL parent_id)                               ├── Spoofable IP auth bypass
  ├── Missing RemoteIpValve (Proxy Ban Risk)                                   ├── Hardcoded SECRET_KEY & IlovePT
  │                                                                            └── Fatal SQL bug in delete_connection
  ▼ (Port 4822)                                                                │
[ Guacamole Proxy Daemon (guacd) ]                                             │ (Spawns containers)
  │                                                                            ▼
  ▼ (Port 5901 - RFB Protocol, unencrypted, securitytypes none)                │
[ Virtualized Desktop Containers (ptvnc1..N) ] ◄───────────────────────────────┘
  ├── Base: Ubuntu 22.04 LTS (Jammy)
  ├── Dual X Servers: Xvfb :1 (wasted RAM) + TurboVNC :2 (active)
  ├── PID 1: runuser (No init/subreaper -> Leaks [AppRun] zombie processes)
  ├── Resource limits: /dev/shm=64M (crashes QtWebEngine), conflicting CPU/RAM
  ├── Runtime Deb Extraction: Uncoordinated concurrent writes to pt_opt
  ├── Application Launch: Fails to detect .AppImage; requires manual start
  └── World-writable shared mount: /shared (no multi-tenant isolation)
```

---

### 1.3 Component & Operational Domain Taxonomy

Each audited finding is categorized across the five core components and five operational domains:

- **Component Definitions**:
  - **Component 1 (C1)**: Virtualized Cisco Packet Tracer Instances (`ptweb-vnc`)
  - **Component 2 (C2)**: Apache Guacamole Stack (`guacd`, `guacamole`, `guacamole-mariadb`)
  - **Component 3 (C3)**: Nginx Edge Gateway (`pt-nginx`)
  - **Component 4 (C4)**: Flask/Gunicorn Management Application (`pt-management`)
  - **Component 5 (C5)**: Deployment Orchestration & Verification Harness (`deploy.sh`, `docker-compose`, etc.)

- **Operational Domain Definitions**:
  - **Security and Hardening (SEC)**: Authentication, authorization, secrets, privileges, network isolation, perimeter controls.
  - **Performance and Resource Scaling (PERF)**: CPU, memory, IPC/shm, concurrency, I/O throughput, streaming responsiveness.
  - **High Availability and Reliability (HA)**: Data persistence, error recovery, process supervision, health probes, failure isolation.
  - **Usability (USE)**: End-user UX, clipboard, audio, multi-tenant workspace isolation, interface responsiveness.
  - **Maintainability (MAINT)**: Code clarity, unified architecture, dependency lifecycle, logging, auditability, operational debt.

---

## 2. Component 1 Audit: Virtualized Cisco Packet Tracer Instances

### 2.1 Component Overview
Component 1 encompasses the desktop virtualization runtime defined in `ptweb-vnc/Dockerfile`, `ptweb-vnc/customizations/start`, `ptweb-vnc/customizations/start-session`, and associated helper scripts. The container runs an XFCE4 desktop session on Ubuntu 22.04 with TurboVNC 3.3 and VirtualGL 3.1.4, hosting proprietary Cisco Packet Tracer binaries delivered via runtime mounting and extraction.

---

### 2.2 Security and Hardening (SEC)

### [FINDING-C1-SEC-01] TurboVNC Invocation with Authentication Disabled (`-securitytypes none`)
- **Target File(s)**: `ptweb-vnc/customizations/start-session`
- **Code Reference**: Lines 73-81 and lines 87-92
  ```bash
  73:         if command -v /opt/TurboVNC/bin/vncserver &>/dev/null; then
  74:             echo "Starting TurboVNC server on port ${VNC_PORT}..."
  75:             DISPLAY=:1 /opt/TurboVNC/bin/vncserver \
  76:               -geometry ${VNC_GEOMETRY} \
  77:               -depth ${VNC_DEPTH} \
  78:               -rfbport ${VNC_PORT} \
  79:               -securitytypes none \
  80:               >/tmp/turbovnc.log 2>&1
  81:         fi
  ...
  87:     DISPLAY=:1 /opt/TurboVNC/bin/vncserver \
  88:       -geometry ${VNC_GEOMETRY} \
  89:       -depth ${VNC_DEPTH} \
  90:       -rfbport ${VNC_PORT} \
  91:       -securitytypes none \
  92:       >/tmp/turbovnc.log 2>&1
  ```
- **Limitation / Vulnerability Description**: Although `start-session` initializes a password file at `/home/ptuser/.vnc/passwd` using `$VNC_PASS` (lines 20-30), the server startup command explicitly passes `-securitytypes none`. This completely disables RFB authentication.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 cat /home/ptuser/.vnc/96c17c1cb30e:2.log | grep -i "security"
  # Output: "Enabled security type 'none'"
  # Output: "Listening for VNC connections on TCP port 5901"
  ```
- **Current Operational Impact**: Severity: HIGH. Any compromised container or rogue actor on the internal Docker bridge network can connect directly to port 5901 of any student's desktop without providing credentials, allowing session hijacking, keystroke monitoring, and unauthorized arbitrary interaction.
- **Recommended Hardening Action & Target Milestone**: Enforce `-securitytypes VncAuth -rfbauth /home/ptuser/.vnc/passwd` or restrict TurboVNC to listen solely on Unix domain sockets (`-localhost`) proxied exclusively via `guacd`. Target: Milestone 2 (M2).

---

### [FINDING-C1-SEC-02] Missing Container Capability Dropping and Root Runtime Privilege Boundaries
- **Target File(s)**: `deploy.sh`, `pt-management/ptmanagement/docker_mgmt/container.py`, `ptweb-vnc/Dockerfile`
- **Code Reference**: `deploy.sh` lines 228-235; `container.py` lines 320-345
  ```bash
  228:     docker run -d \
  229:       --name ptvnc$i --restart unless-stopped \
  230:       --network ptnet \
  231:       --cpus=0.5 -m 2G --ulimit nproc=2048 --ulimit nofile=1024 \
  232:       --dns=127.0.0.1 \
  233:       -v pt_opt:/opt/pt \
  234:       --mount type=bind,source="${WORKDIR}/shared",target=/shared,bind-propagation=rprivate \
  235:       ptvnc
  ```
- **Limitation / Vulnerability Description**: Containers are provisioned without dropping Linux capabilities (`--cap-drop=ALL`) and without enabling `--security-opt=no-new-privileges:true`. Inside `ptweb-vnc/Dockerfile`, `/start` runs initially as root before invoking `runuser` to switch to `ptuser`. No seccomp profile or AppArmor profile is enforced.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker inspect ptvnc1 --format '{{.HostConfig.CapDrop}} {{.HostConfig.SecurityOpt}}'
  # Output: [] [] (Empty array; all default Linux capabilities retained)
  ```
- **Current Operational Impact**: Severity: MEDIUM. If an adversary escapes the Packet Tracer application or QtWebEngine sandbox, retained kernel capabilities (e.g., `CAP_NET_RAW`, `CAP_SYS_CHROOT`, `CAP_MKNOD`) significantly increase the attack surface for container breakout.
- **Recommended Hardening Action & Target Milestone**: Apply `--cap-drop=ALL --cap-add=CHOWN --cap-add=SETUID --cap-add=SETGID`, enforce `no-new-privileges`, and configure rootless container execution. Target: Milestone 3 (M3).

---

### 2.3 Performance and Resource Scaling (PERF)

### [FINDING-C1-PERF-01] Concurrent Dual X Display Servers (`Xvfb :1` and `TurboVNC :2`) Wasting Memory
- **Target File(s)**: `ptweb-vnc/customizations/start-session`
- **Code Reference**: Lines 38-42, 50-54, and 86-95
  ```bash
  38: echo "Starting Xvfb virtual display :1..."
  39: Xvfb :1 -screen 0 ${VNC_GEOMETRY}x${VNC_DEPTH} -nolisten tcp -dpi 96 >/tmp/xvfb.log 2>&1 &
  ...
  52: DISPLAY=:1 XAUTHORITY=/home/ptuser/.Xauthority su - ptuser -c "startxfce4" >/tmp/xfce.log 2>&1 &
  ...
  87: DISPLAY=:1 /opt/TurboVNC/bin/vncserver \
  88:   -geometry ${VNC_GEOMETRY} \
  89:   -depth ${VNC_DEPTH} \
  90:   -rfbport ${VNC_PORT} \
  91:   -securitytypes none \
  92:   >/tmp/turbovnc.log 2>&1
  ```
- **Limitation / Vulnerability Description**: `start-session` initializes `Xvfb` on display `:1`. Later in the script, it executes TurboVNC (`vncserver`), which attempts to bind to display `:1`. Because `:1` is already occupied by `Xvfb`, TurboVNC bumps the display to `:2` and launches its own independent X server (`Xvnc :2`). `Xvfb :1` remains running as an orphaned, completely idle background process.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 ps aux | grep -E "Xvfb|Xvnc"
  # Output:
  # ptuser 23  ... 208848  66688 ? S 12:54 0:00 Xvfb :1 -screen 0 1280x720x24 -nolisten tcp -dpi 96
  # ptuser 66  ... 348604 140616 ? S 12:54 0:04 /opt/TurboVNC/bin/Xvnc :2 ...
  ```
- **Current Operational Impact**: Severity: HIGH. Each container wastes ~208MB virtual memory and ~66MB RSS running an unused X server. Across 30 concurrent student instances, this wastes ~2GB of host RAM with zero utility.
- **Recommended Hardening Action & Target Milestone**: Remove `Xvfb` completely. Launch TurboVNC directly on display `:1` as the sole X11 and VNC server. Target: Milestone 2 (M2).

---

### [FINDING-C1-PERF-02] Chromium / QtWebEngine Shared Memory Exhaustion via 64MB Default `/dev/shm`
- **Target File(s)**: `deploy.sh`, `pt-management/ptmanagement/docker_mgmt/container.py`, `ptweb-vnc/docker-compose.yml`
- **Code Reference**: `deploy.sh` line 231; `container.py` line 333
- **Limitation / Vulnerability Description**: Cisco Packet Tracer versions 8.x and 9.x integrate multiple `QtWebEngineProcess` instances for authentication dialogs, embedded documentation, and interactive tutorials. QtWebEngine is built on Chromium, which relies extensively on POSIX shared memory (`/dev/shm`) for inter-process communication, pixmap buffers, and rendering pipelines. The default Docker shared memory allocation is only 64MB (`67108864` bytes).
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker inspect ptvnc1 --format '{{.HostConfig.ShmSize}}'
  # Output: 67108864 (64MB)
  ```
- **Current Operational Impact**: Severity: HIGH. When multiple graphical windows or simulation panels are opened simultaneously, Chromium processes encounter `OOM / ENOSPC` on `/dev/shm`, causing browser tabs and Packet Tracer child panels to crash abruptly with `SIGBUS` or silent rendering blankouts.
- **Recommended Hardening Action & Target Milestone**: Explicitly configure `--shm-size=512m` across all deployment scripts, Docker Compose definitions, and Python container creation routines. Target: Milestone 2 (M2).

---

### [FINDING-C1-PERF-03] Low File Descriptor and Process Limits (`nofile=1024`, `nproc=2048`) Under Multi-Window Labs
- **Target File(s)**: `deploy.sh`, `add-instance.sh`, `pt-management/ptmanagement/api/routes.py`
- **Code Reference**: `deploy.sh` line 231; `routes.py` line 208
  ```bash
  deploy.sh:231: --ulimit nproc=2048 --ulimit nofile=1024
  routes.py:208: '--ulimit', 'nproc=2048', '--ulimit', 'nofile=1024',
  ```
- **Limitation / Vulnerability Description**: Modern Linux desktops running XFCE4, TurboVNC, VirtualGL, and Packet Tracer with 6+ `QtWebEngineProcess` child threads open a substantial number of socket handles, shared memory file descriptors, font files, and IPC pipes. A soft/hard limit of 1024 file descriptors is dangerously low for a multi-threaded GUI environment.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker inspect ptvnc1 --format '{{json .HostConfig.Ulimits}}'
  # Output: [{"Hard":1024,"Name":"nofile","Soft":1024},{"Hard":2048,"Name":"nproc","Soft":2048}]
  ```
- **Current Operational Impact**: Severity: MEDIUM. During complex multi-device network simulations, socket opening or file caching operations fail with `EMFILE: Too many open files`, causing Packet Tracer to lock up or lose unsaved student network topologies.
- **Recommended Hardening Action & Target Milestone**: Increase limits to `--ulimit nofile=65536:65536 --ulimit nproc=4096:4096`. Target: Milestone 2 (M2).

---

### 2.4 High Availability and Reliability (HA)

### [FINDING-C1-HA-01] PID 1 Without Subreaper Leaking Defunct Zombie Processes (`[AppRun] <defunct>`)
- **Target File(s)**: `ptweb-vnc/Dockerfile`, `ptweb-vnc/customizations/start`
- **Code Reference**: `Dockerfile` line 131 (`ENTRYPOINT ["/start"]`); `start` line 21 (`exec runuser -u ptuser /start-session`)
- **Limitation / Vulnerability Description**: Docker containers require an init process at PID 1 capable of reaping orphaned zombie processes (`SIGCHLD`). In `ptweb-vnc`, PID 1 is `/bin/sh` or `runuser`, which lacks child reaping capabilities. Whenever Packet Tracer launches helper binaries or AppImage squashfs extractors that fork and terminate, the kernel retains their terminated state in the process table.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 ps aux | grep defunct
  # Output:
  # ptuser 309  0.0  0.0  0  0 ?  Z  12:59  0:00 [AppRun] <defunct>
  # ptuser 314  0.0  0.0  0  0 ?  Z  12:59  0:00 [AppRun] <defunct>
  # ptuser 319  0.0  0.0  0  0 ?  Z  12:59  0:00 [AppRun] <defunct>
  # ptuser 324  0.0  0.0  0  0 ?  Z  12:59  0:00 [AppRun] <defunct>
  # ptuser 330  0.0  0.0  0  0 ?  Z  12:59  0:00 [AppRun] <defunct>
  # ptuser 473  0.0  0.0  0  0 ?  Z  13:00  0:00 [xfce4-mime-help] <defunct>
  ```
- **Current Operational Impact**: Severity: HIGH. Over days of classroom lab usage, defunct processes accumulate monotonically until the container hits its process limit (`nproc=2048`), causing `fork: Resource temporarily unavailable` and completely crashing student sessions.
- **Recommended Hardening Action & Target Milestone**: Introduce `tini` or `dumb-init` as the container entrypoint (`ENTRYPOINT ["/usr/bin/tini", "--", "/start"]`). Target: Milestone 2 (M2).

---

### [FINDING-C1-HA-02] Uncoordinated Concurrent Deb Extraction on Shared Named Volume `pt_opt`
- **Target File(s)**: `ptweb-vnc/customizations/start`, `ptweb-vnc/customizations/runtime-install.sh`, `ptweb-vnc/customizations/pt-install.sh`
- **Code Reference**: `start` line 11; `runtime-install.sh` lines 87-93 (specifically lines 90-91)
  ```bash
  start:11: /runtime-install.sh &>/tmp/runtime-install.log &
  runtime-install.sh:90: cp -f "$debfile" /PacketTracer.deb || true
  runtime-install.sh:91: if /pt-install.sh; then
  ```
- **Limitation / Vulnerability Description**: All `ptvnc*` containers mount the identical shared named volume `pt_opt` to `/opt/pt`. On startup, every container runs `/runtime-install.sh` in the background. Because `pt-install.sh` fails detection (Finding C1-HA-03), marker files are never permanently saved. Consequently, during a batch boot (e.g. 10 containers starting simultaneously), all 10 containers concurrently execute `dpkg-deb -x` and write files into `/opt/pt` without mutex locks.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker logs ptvnc1 2>&1 | grep -i "install"
  # Concurrent overwrites and partial binary corruption in /opt/pt observed under parallel scale-up.
  ```
- **Current Operational Impact**: Severity: HIGH. Causes severe disk I/O thrashing and high risk of file corruption within `/opt/pt`, leaving Packet Tracer binaries in a corrupted, non-executable state.
- **Recommended Hardening Action & Target Milestone**: Implement file locking (`flock`) on a volume-level lockfile, or adopt an init-container pattern where an installer container runs once to completion before any desktop instances boot. Target: Milestone 2 (M2).

---

### [FINDING-C1-HA-03] Silent Application Launch Failure Due to Missing AppImage Executable Detection
- **Target File(s)**: `ptweb-vnc/customizations/pt-install.sh`, `ptweb-vnc/customizations/start-session`
- **Code Reference**: `pt-install.sh` lines 70-75; `start-session` lines 103-107
  ```bash
  pt-install.sh:70:
  if [ -x /opt/pt/packettracer ] || [ -x /opt/pt/bin/PacketTracer ]; then
    log_progress "✓ SUCCESS: PacketTracer installed and ready!"
  else
    log_progress "✗ FATAL ERROR: PacketTracer installation failed"
  ```
- **Limitation / Vulnerability Description**: Modern Cisco Packet Tracer deb packages extract `/opt/pt/packettracer.AppImage`. The installer validation logic in `pt-install.sh` checks only for `/opt/pt/packettracer` and `/opt/pt/bin/PacketTracer`. Failing to find either, it prints a fatal error and exits with code 1. Furthermore, `start-session` line 103 checks for `/opt/pt/squashfs-root/AppRun`. Because runtime extraction unpacks into `/tmp`, `start-session` fails its condition and skips auto-launching Packet Tracer entirely.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 cat /tmp/runtime-install.log
  # Output: "[pt-install] ✗ FATAL ERROR: PacketTracer installation failed"
  # Output: "Expected executables not found: /opt/pt/packettracer, /opt/pt/bin/PacketTracer"
  # Output: "Actual /opt/pt contents: packettracer.AppImage"
  ```
- **Current Operational Impact**: Severity: HIGH. The desktop loads an empty XFCE desktop without Packet Tracer running. Students must manually locate and double-click desktop icons, and container logs report continuous fatal installation errors.
- **Recommended Hardening Action & Target Milestone**: Update `pt-install.sh` and `start-session` to recognize `packettracer.AppImage`, create the canonical symlink `/opt/pt/packettracer`, and extract the AppImage during build/init. Target: Milestone 2 (M2).

---

### 2.5 Usability (USE)

### [FINDING-C1-USE-01] Broken Clipboard Synchronization via Unexecuted `autocutsel` Configuration
- **Target File(s)**: `ptweb-vnc/customizations/home/ptuser/.vnc/xstartup`, `ptweb-vnc/customizations/start-session`
- **Code Reference**: `xstartup` line 15 (`/usr/bin/autocutsel -s CLIPBOARD -fork 2>/dev/null || true`)
- **Limitation / Vulnerability Description**: Bidirectional clipboard synchronization between the client browser and the virtual X11 desktop requires `autocutsel` to bridge X11 `PRIMARY` selection and the modern `CLIPBOARD` buffer. While `autocutsel` is configured in `/home/ptuser/.vnc/xstartup`, TurboVNC defaults to executing `/opt/TurboVNC/bin/xstartup.turbovnc`, bypassing the user's custom `xstartup` script entirely.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 ps aux | grep autocutsel
  # Output: (Empty; autocutsel is not running)
  ```
- **Current Operational Impact**: Severity: MEDIUM. Students cannot copy router configuration snippets, IP addressing tables, or Python scripts from their host browser into Packet Tracer, severely degrading laboratory usability.
- **Recommended Hardening Action & Target Milestone**: Add `/usr/bin/autocutsel -s CLIPBOARD -fork` directly into the master session startup script or configure `/etc/turbovncserver.conf` to execute the user's `xstartup`. Target: Milestone 2 (M2).

---

### [FINDING-C1-USE-02] Absence of Virtual Audio Subsystem and PulseAudio Integration
- **Target File(s)**: `ptweb-vnc/Dockerfile`, `ptweb-vnc/customizations/start-session`
- **Code Reference**: Entire Component 1 pipeline
- **Limitation / Vulnerability Description**: No PulseAudio or ALSA sound subsystem is configured inside the desktop container. While Packet Tracer is primarily a visual network simulator, modern multimedia lab modules, accessibility screen readers, and auditory cue plugins generate audio events that are dropped.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 ps aux | grep -i pulse
  # Output: (Empty)
  ```
- **Current Operational Impact**: Severity: LOW. Complete absence of audio capabilities prevents accessibility features and auditory feedback.
- **Recommended Hardening Action & Target Milestone**: Evaluate PulseAudio dummy sink streaming over Guacamole's native audio pipeline in future enhancements. Target: Milestone 4 (M4).

---

### 2.6 Maintainability (MAINT)

### [FINDING-C1-MAINT-01] Failed `su - ptuser` Invocation via Unset Password During Container Startup
- **Target File(s)**: `ptweb-vnc/customizations/start-session`
- **Code Reference**: Lines 52, 111, 125
  ```bash
  52: DISPLAY=:1 XAUTHORITY=/home/ptuser/.Xauthority su - ptuser -c "startxfce4" >/tmp/xfce.log 2>&1 &
  ```
- **Limitation / Vulnerability Description**: Container entrypoint `/start` switches to `ptuser` using `runuser -u ptuser /start-session`. Consequently, `start-session` runs as the unprivileged user `ptuser`. Line 52 then attempts to execute `su - ptuser -c "startxfce4"`. Because `ptuser` has no password set in `/etc/shadow` and non-root users cannot invoke `su` without authenticating, the command immediately aborts with an authentication failure.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 cat /tmp/xfce.log
  # Output: "Password: su: Authentication failure"
  ```
- **Current Operational Impact**: Severity: MEDIUM. Pollutes container startup logs with authentication failures and causes XFCE desktop components to start in a broken or fallback state.
- **Recommended Hardening Action & Target Milestone**: Remove all redundant `su` calls from `start-session`. Since the script already runs as `ptuser`, commands should be executed directly. Target: Milestone 2 (M2).

---

### [FINDING-C1-MAINT-02] Dead Code and Mismatched Protocol Artifacts (`startwm-pt.sh`, `verify-rdp-deployment.sh`)
- **Target File(s)**: `ptweb-vnc/customizations/startwm-pt.sh`, `verify-rdp-deployment.sh`
- **Code Reference**: `startwm-pt.sh` lines 1-40; `verify-rdp-deployment.sh` lines 1-100
- **Limitation / Vulnerability Description**: The repository contains conflicting legacy scripts designed for XRDP deployments (testing port 3389 and XRDP processes), whereas the active production stack utilizes VNC (RFB on port 5901).
- **Empirical Evidence / Reproduction Command**:
  ```bash
  bash verify-rdp-deployment.sh
  # Output: Multiple failure messages checking for non-existent /usr/sbin/xrdp and port 3389
  ```
- **Current Operational Impact**: Severity: LOW. Misleads operators during troubleshooting and creates false negatives in automated verification suites.
- **Recommended Hardening Action & Target Milestone**: Deprecate and remove obsolete XRDP artifacts from the repository. Target: Milestone 2 (M2).

---

## 3. Component 2 Audit: Apache Guacamole Stack

### 3.1 Component Overview
Component 2 consists of the Apache Guacamole clientless remote desktop gateway, comprised of the `guacd` proxy daemon, the `pt-guacamole` Java/Tomcat web application, and the `guacamole-mariadb` database backend storing user records, permissions, and connection parameters.

---

### 3.2 Security and Hardening (SEC)

### [FINDING-C2-SEC-01] Hardcoded Database Credentials and Password Inconsistencies Across Components
- **Target File(s)**: `deploy.sh`, `deploy-full.sh`, `ptweb-vnc/docker-compose.yml`, `pt-management/ptmanagement/db/connection.py`, `generate-dynamic-connections.sh`, `health_check.sh`
- **Code Reference**: `deploy.sh` lines 21-23; `connection.py` lines 19-20; `docker-compose.yml` lines 13-14
  ```bash
  deploy.sh:21: dbuser="ptdbuser"
  deploy.sh:22: dbpass="ptdbpass"
  connection.py:19: user=os.environ.get('DB_USER', 'ptdbuser'),
  connection.py:20: password=os.environ.get('DB_PASS', 'ptdbpass'),
  docker-compose.yml:85: DB_PASSWORD: ptdbpass
  ```
- **Limitation / Vulnerability Description**: Database credentials (`ptdbuser` / `ptdbpass`) are hardcoded across at least 8 distinct files in the repository. Furthermore, there is a naming discrepancy: `connection.py` expects `DB_PASS`, whereas `docker-compose.yml` and `deploy-full.sh` provide `DB_PASSWORD`. Consequently, overriding `DB_PASSWORD` via environment variables is silently ignored by the Python backend, which falls back to the hardcoded default `ptdbpass`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "ptdbpass" deploy.sh ptweb-vnc/ pt-management/
  # Matches found in 8+ source files across shell, python, SQL, and YAML.
  ```
- **Current Operational Impact**: Severity: HIGH. Prevents credential rotation in production environments and exposes the backend database to unauthorized access if internal network boundaries are breached.
- **Recommended Hardening Action & Target Milestone**: Standardize on `DB_PASSWORD`, enforce dynamic credential generation on initial deployment, and support Docker Secrets. Target: Milestone 2 (M2).

---

### [FINDING-C2-SEC-02] Default Administrative Credentials and Unrotated Authentication Hashes
- **Target File(s)**: `ptweb-vnc/db-dump.sql`, `pt-management/ptmanagement/api/auth.py`, `deploy-full.sh`
- **Code Reference**: `db-dump.sql` line 458; `auth.py` lines 181-185
  ```python
  auth.py:181:
      ptadmin_password = os.environ.get('PTADMIN_PASSWORD', 'IlovePT')
      if username == 'ptadmin' and password == ptadmin_password:
          logger.info(f"✓ Default ptadmin authentication successful")
          return True
  ```
- **Limitation / Vulnerability Description**: The baseline database dump (`db-dump.sql`) pre-seeds a default administrator account (`ptadmin`) with a static password hash dating back to March 2020. In parallel, `auth.py` implements a hardcoded fallback check allowing login with `IlovePT` if `PTADMIN_PASSWORD` is not explicitly set.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "IlovePT" .
  # Confirmed in auth.py, deploy-full.sh, docker-compose.yml, and test-bulk-delete.sh.
  ```
- **Current Operational Impact**: Severity: HIGH. Default administrative accounts remain vulnerable to unauthorized access if deployments fail to override `.env` settings.
- **Recommended Hardening Action & Target Milestone**: Remove hardcoded fallbacks in `auth.py`. Require administrator password initialization during initial setup wizard or automated deployment script. Target: Milestone 2 (M2).

---

### 3.3 Performance and Resource Scaling (PERF)

### [FINDING-C2-PERF-01] Absence of Nginx Reverse Proxy Buffering Disablement for Guacamole Streams
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 70-83
  ```nginx
  70:     # WebSocket support for Guacamole tunneling
  71:     proxy_http_version 1.1;
  72:     proxy_set_header Upgrade $http_upgrade;
  73:     proxy_set_header Connection "upgrade";
  74:     ...
  81:     proxy_buffers 32 4k;
  82:     proxy_pass http://pt-guacamole:8080/guacamole/;
  ```
- **Limitation / Vulnerability Description**: Guacamole's HTTP and WebSocket streaming tunnels require real-time, unbuffered packet delivery between the browser and Tomcat. The official Apache Guacamole documentation explicitly mandates `proxy_buffering off;`. In `ptweb.conf`, `proxy_buffering off;` is completely omitted, leaving Nginx's default response buffering enabled with `proxy_buffers 32 4k;`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec pt-nginx1 grep -i "proxy_buffering" /etc/nginx/conf.d/ptweb.conf
  # Output: (Returncode 1; directive is absent)
  ```
- **Current Operational Impact**: Severity: HIGH. Introduces substantial latency, mouse pointer jitter, and stuttering during packet trace animations and device drag-and-drop operations.
- **Recommended Hardening Action & Target Milestone**: Add `proxy_buffering off;` to the Guacamole proxy location block in Nginx configuration. Target: Milestone 2 (M2).

---

### [FINDING-C2-PERF-02] Missing Guacamole Connection Parameter Tuning for Screen Updates and Frame Rates
- **Target File(s)**: `generate-dynamic-connections.sh`, `ptweb-vnc/db-dump.sql`, `pt-management/ptmanagement/db/guacamole.py`
- **Code Reference**: `generate-dynamic-connections.sh` lines 73-78
  ```sql
  INSERT IGNORE INTO `guacamole_connection_parameter` 
  (`connection_id`, `parameter_name`, `parameter_value`) 
  VALUES 
    ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'hostname', 'ptvnc$instance_num'),
    ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'port', '5901'),
    ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'username', 'ptuser'),
    ((SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name'), 'password', 'Cisco123');
  ```
- **Limitation / Vulnerability Description**: Guacamole supports advanced connection tuning parameters (`color-depth`, `cursor`, `autoreconnect`, `enable-audio`, `clipboard-encoding`). Currently, only basic connection coordinates (`hostname`, `port`, `username`, `password`) are injected. Essential parameters for bandwidth reduction (`color-depth: 16` or `24`, `cursor: local`) are missing.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -e "SELECT DISTINCT parameter_name FROM guacamole_connection_parameter;"
  # Output: hostname, password, port, security, username (Only 5 basic parameters present)
  ```
- **Current Operational Impact**: Severity: MEDIUM. Results in suboptimal network bandwidth usage and client-side cursor latency over WAN/VPN connections.
- **Recommended Hardening Action & Target Milestone**: Inject optimized Guacamole connection parameters during connection provisioning. Target: Milestone 2 (M2).

---

### 3.4 High Availability and Reliability (HA)

### [FINDING-C2-HA-01] Anonymous Docker Volume for MariaDB Leading to Total Data Loss on Recreate
- **Target File(s)**: `deploy.sh`, `ptweb-vnc/docker-compose.yml`
- **Code Reference**: `deploy.sh` line 191; `docker-compose.yml` lines 15-16
  ```yaml
  docker-compose.yml:15:
      volumes:
        - ./db-dump.sql:/docker-entrypoint-initdb.d/db-dump.sql:ro
  deploy.sh:191:
      -v dbdump:/docker-entrypoint-initdb.d \
  ```
- **Limitation / Vulnerability Description**: Neither `deploy.sh` nor `docker-compose.yml` specifies a persistent named volume or host bind-mount for MariaDB's database storage directory (`/var/lib/mysql`). The Docker daemon assigns an anonymous volume with an arbitrary 64-character hash name.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker inspect guacamole-mariadb --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Type}}: {{.Name}}{{end}}{{end}}'
  # Output: volume: b8c4092bc87e9898ebc3327fe99302538d509f44877756cdb7322dedad7ee98c
  ```
- **Current Operational Impact**: Severity: CRITICAL. Executing `docker-compose down -v` or `deploy.sh recreate` permanently destroys all student user accounts, password hashes, laboratory assignments, connection histories, and active container mappings.
- **Recommended Hardening Action & Target Milestone**: Explicitly define a persistent named volume `mariadb_data:/var/lib/mysql` in `docker-compose.yml` and `deploy.sh`. Target: Milestone 2 (M2).

---

### [FINDING-C2-HA-02] Guacamole Connection Deduplication Failure via `NULL` Parent ID in MariaDB
- **Target File(s)**: `generate-dynamic-connections.sh`, `ptweb-vnc/db-dump.sql`
- **Code Reference**: `db-dump.sql` line 28; `generate-dynamic-connections.sh` lines 58-62
  ```sql
  db-dump.sql:28: UNIQUE KEY `connection_name_parent` (`connection_name`,`parent_id`),
  generate-dynamic-connections.sh:58:
  INSERT IGNORE INTO `guacamole_connection` 
  (`connection_name`, `protocol`, `proxy_port`, `proxy_hostname`, `proxy_encryption_method`, `max_connections`, `max_connections_per_user`, `failover_only`) 
  VALUES ('$connection_name', 'vnc', 4822, 'pt-guacd', 'NONE', 1, 1, 0);
  ```
- **Limitation / Vulnerability Description**: In SQL-92 standards, `NULL = NULL` evaluates to `UNKNOWN`. MariaDB/MySQL adheres to this standard: a unique index over `(connection_name, parent_id)` permits duplicate rows if `parent_id` is `NULL`. `db-dump.sql` pre-populates connections `pt01` and `pt02` with `parent_id=NULL`. When `generate-dynamic-connections.sh` runs `INSERT IGNORE`, MariaDB inserts duplicate rows (IDs 3 and 4). Later, when parameter insertion executes `(SELECT connection_id FROM guacamole_connection WHERE connection_name = '$connection_name')`, the scalar subquery returns multiple rows or attaches parameters only to ID 1, leaving duplicate connections unconfigured.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -e "SELECT connection_id, connection_name, parent_id FROM guacamole_connection;"
  # Output:
  # 1  pt01  NULL
  # 2  pt02  NULL
  # 3  pt01  NULL  (Duplicate with 0 parameters)
  # 4  pt02  NULL  (Duplicate with 0 parameters)
  ```
- **Current Operational Impact**: Severity: HIGH. Causes duplicate connection tiles in the Guacamole web UI, where half of the connection links fail to connect due to missing parameters.
- **Recommended Hardening Action & Target Milestone**: Update `generate-dynamic-connections.sh` to explicitly check and delete existing records where `parent_id IS NULL`, or assign root connection group `parent_id=ROOT`. Target: Milestone 2 (M2).

---

### [FINDING-C2-HA-03] Nginx Reverse Proxy IP Ban Lockout via Tomcat RemoteIpValve Omission
- **Target File(s)**: `ptweb-vnc/docker-compose.yml`, `deploy.sh`
- **Code Reference**: Tomcat configuration in `guacamole/guacamole` image
- **Limitation / Vulnerability Description**: Guacamole includes an automated brute-force authentication protection mechanism (`BanningAuthenticationListener`) that bans IP addresses for 300 seconds after 5 failed authentication attempts. Because the Tomcat servlet container lacks `RemoteIpValve` configuration in `server.xml`, Tomcat logs the incoming TCP connection address (the Nginx reverse proxy IP `172.18.0.x`) rather than the client's public IP from `X-Forwarded-For`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker logs pt-guacamole 2>&1 | grep "BanningAuthenticationListener"
  # Output: "Addresses will be automatically banned for 300 seconds after 5 failed authentication attempts."
  # Authenticated logs show proxy IPs: "User ptadmin authenticated from [172.19.0.1, 172.18.0.7]"
  ```
- **Current Operational Impact**: Severity: HIGH. If an external attacker or student enters an incorrect password 5 times, Guacamole bans the Nginx proxy IP address, locking out all students and instructors across the entire institution for 5 minutes.
- **Recommended Hardening Action & Target Milestone**: Configure `RemoteIpValve` in Tomcat's `server.xml` or mount a custom configuration file into `pt-guacamole`. Target: Milestone 2 (M2).

---

### 3.5 Usability (USE)

### [FINDING-C2-USE-01] Disruptive Active User Disconnections on Container Scale-in Deprovisioning
- **Target File(s)**: `remove-instance.sh`
- **Code Reference**: Lines 148-180 and 227-229
  ```bash
  148: # Stop and remove old guacd
  149: docker stop pt-guacd 2>/dev/null || true
  150: docker rm pt-guacd 2>/dev/null || true
  ...
  165: # Recreate guacamole
  166: docker stop pt-guacamole 2>/dev/null || true
  167: docker rm pt-guacamole 2>/dev/null || true
  ...
  228: echo "Active users were disconnected during the removal process."
  ```
- **Limitation / Vulnerability Description**: To remove a single `ptvnc` container, `remove-instance.sh` forcibly tears down and recreates `pt-guacd`, `pt-guacamole`, and `pt-nginx1`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n -C 2 "Active users were disconnected" remove-instance.sh
  # Verified verbatim in script warnings.
  ```
- **Current Operational Impact**: Severity: HIGH. Routine administrative deprovisioning of an idle student instance forcibly terminates all active sessions across all students in other instances.
- **Recommended Hardening Action & Target Milestone**: Refactor `remove-instance.sh` to remove only the targeted container and delete its corresponding MariaDB connection record, requiring zero container restarts. Target: Milestone 2 (M2).

---

### [FINDING-C2-USE-02] Orphaned and Broken Connections in UI Caused by Dynamic Connection Subquery Bugs
- **Target File(s)**: `generate-dynamic-connections.sh`
- **Code Reference**: Lines 65-78
- **Limitation / Vulnerability Description**: As established in Finding C2-HA-02, duplicate connection rows are created with identical names. In the Guacamole web interface, students and instructors see multiple instances of `pt01` and `pt02`, one of which displays a connection failure banner upon clicking.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -e "SELECT * FROM guacamole_connection_parameter WHERE connection_id IN (3, 4);"
  # Output: Empty set (Connections 3 and 4 have 0 parameters)
  ```
- **Current Operational Impact**: Severity: MEDIUM. Causes user confusion, support tickets, and perceived system unreliability.
- **Recommended Hardening Action & Target Milestone**: Deduplicate database connections and sanitize schema insertion scripts. Target: Milestone 2 (M2).

---

### 3.6 Maintainability (MAINT)

### [FINDING-C2-MAINT-01] Unpinned Image Tags (`mariadb:latest`, `guacamole/guacd:latest`, `guacamole/guacamole`)
- **Target File(s)**: `deploy.sh`, `ptweb-vnc/docker-compose.yml`
- **Code Reference**: `deploy.sh` lines 197, 258; `docker-compose.yml` lines 5, 20, 27
  ```bash
  deploy.sh:197: -d mariadb:latest
  deploy.sh:258: -d guacamole/guacd:latest
  docker-compose.yml:27: image: guacamole/guacamole
  ```
- **Limitation / Vulnerability Description**: Upstream container images use unpinned `:latest` or omitted tags.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -E "image:.*(latest|$)" ptweb-vnc/docker-compose.yml
  # Shows unpinned tags across database and gateway components.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Deployments on different dates pull different minor/major versions, leading to unreproducible builds and subtle schema/API incompatibilities.
- **Recommended Hardening Action & Target Milestone**: Pin explicit upstream version tags (e.g. `mariadb:10.11`, `guacamole/guacd:1.5.5`, `guacamole/guacamole:1.5.5`). Target: Milestone 2 (M2).

---

### [FINDING-C2-MAINT-02] Orphaned Configuration Files with Hardcoded Bridge IPs (`guacamole.properties`)
- **Target File(s)**: `guacamole.properties`
- **Code Reference**: Lines 7-8
  ```properties
  guacd-hostname: 172.17.0.5
  guacd-port: 4822
  ```
- **Limitation / Vulnerability Description**: The root directory contains `guacamole.properties` with a hardcoded Docker default bridge IP (`172.17.0.5`). This file is not mounted into any active container and represents dead configuration debt.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "guacamole.properties" ptweb-vnc/ deploy.sh deploy-full.sh
  # Output: (No mount references found)
  ```
- **Current Operational Impact**: Severity: LOW. Confuses operators attempting to modify Guacamole daemon connection properties.
- **Recommended Hardening Action & Target Milestone**: Remove obsolete root-level `guacamole.properties`. Target: Milestone 2 (M2).

---

## 4. Component 3 Audit: Nginx Edge Gateway

### 4.1 Component Overview
Component 3 is the edge reverse proxy and TLS gateway defined in `ptweb-vnc/pt-nginx/Dockerfile`, `ptweb-vnc/pt-nginx/nginx.conf`, and `ptweb-vnc/pt-nginx/generate-nginx-conf.sh`. It handles HTTPS termination on ports 443 and 5000, GeoIP filtering, rate limiting, and traffic routing to Guacamole and Flask management services.

---

### 4.2 Security and Hardening (SEC)

### [FINDING-C3-SEC-01] Deprecated Legacy GeoIP1 Format Downloaded from Untrusted Third-Party Domain
- **Target File(s)**: `ptweb-vnc/pt-nginx/Dockerfile`, `deploy.sh`
- **Code Reference**: `Dockerfile` line 30 (`--with-http_geoip_module`); `deploy.sh` lines 160-165
  ```bash
  160: GEOIP_URL="https://mailfud.org/geoip-legacy/GeoIP.dat.gz"
  161: TEMP_GZ="${GEOIP_DIR}/GeoIP.dat.gz"
  162: if wget -q -O "$TEMP_GZ" "$GEOIP_URL" 2>/dev/null; then
  163:     gunzip -f "$TEMP_GZ"
  ```
- **Limitation / Vulnerability Description**: Nginx is compiled with `--with-http_geoip_module`, which supports only the legacy MaxMind GeoIP v1 format (`.dat`). MaxMind officially discontinued GeoIP v1 in January 2019. To obtain a database, `deploy.sh` downloads an unverified binary from an unofficial personal domain (`mailfud.org`) without checksum, GPG signature, or TLS pinning.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -E "http_geoip_module|mailfud" ptweb-vnc/pt-nginx/Dockerfile deploy.sh
  # Confirmed legacy compilation and third-party download source.
  ```
- **Current Operational Impact**: Severity: HIGH. Supply-chain risk via unverified binary download; outdated IP geolocations leading to false-positive blocks and false-negative bypasses.
- **Recommended Hardening Action & Target Milestone**: Migrate to modern MaxMind GeoIP2 module (`ngx_http_geoip2_module`) using official `.mmdb` databases with automated updater tooling. Target: Milestone 2 (M2).

---

### [FINDING-C3-SEC-02] Flawed ISO Country Codes (`UK`, `SL`) and Regex Bypass Vulnerability in Trusted IPs Map
- **Target File(s)**: `ptweb-vnc/pt-nginx/nginx.conf`, `ptweb-vnc/pt-nginx/generate-nginx-conf.sh`, `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: `nginx.conf` lines 44-50; `generate-nginx-conf.sh` lines 55-75; `ptweb.conf` lines 30-36
  ```nginx
  nginx.conf:44:
      map $geoip_country_code $allowed_country {
          default 0;
          FI 1;
          SL 1;
          UK 1;
          US 1;
      }
  ptweb.conf:30:
      if ($remote_addr ~ ^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)|86.50.84.227) {
  ```
- **Limitation / Vulnerability Description**:
  1. `UK` is NOT an ISO 3166-1 alpha-2 code; the official code is `GB`. MaxMind databases return `GB`. Legitimate traffic from the United Kingdom is assigned country code `GB`, fails the whitelist match, and is dropped with HTTP 444.
  2. `SL` is Sierra Leone, whereas the intended country was likely Sri Lanka (`LK`).
  3. The bypass regex `^(...)|86.50.84.227` contains an unanchored alternative (`|86.50.84.227`), and dots are unescaped regex wildcards. Any client IP containing `86X50X84X227` anywhere in its string matches the expression, bypassing GeoIP filtering entirely.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n -C 3 "UK 1;" ptweb-vnc/pt-nginx/nginx.conf
  # Shows invalid ISO code 'UK'.
  ```
- **Current Operational Impact**: Severity: HIGH. Legitimate UK students are locked out, while external attackers can craft IP strings that bypass perimeter filtering.
- **Recommended Hardening Action & Target Milestone**: Fix ISO codes to `GB` and `LK`. Replace fragile `if` location regexes with top-level Nginx `geo` and `map` blocks. Target: Milestone 2 (M2).

---

### [FINDING-C3-SEC-03] Permissive TLS Ciphers, Missing OCSP Stapling, and Absence of HSTS / Security Headers
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 20-25
  ```nginx
  20: ssl_certificate /etc/ssl/certs/server.crt;
  21: ssl_certificate_key /etc/ssl/private/server.key;
  22: ssl_protocols TLSv1.2 TLSv1.3;
  23: ssl_ciphers HIGH:!aNULL:!MD5;
  24: ssl_prefer_server_ciphers on;
  ```
- **Limitation / Vulnerability Description**: The cipher suite `HIGH:!aNULL:!MD5` permits deprecated 3DES and non-PFS ciphers under TLS 1.2. `Strict-Transport-Security` (HSTS), `X-Frame-Options`, `X-Content-Type-Options: nosniff`, `Content-Security-Policy` (CSP), and `Referrer-Policy` headers are completely absent. OCSP stapling is not enabled.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  curl -k -I https://localhost/
  # Output reveals zero security headers and Server: nginx/1.27.0 banner.
  ```
- **Current Operational Impact**: Severity: HIGH. Leaves web portal vulnerable to clickjacking, MIME-type sniffing, downgrade attacks, and server banner fingerprinting.
- **Recommended Hardening Action & Target Milestone**: Enforce Mozilla Intermediate cipher suites, inject comprehensive security headers, enable OCSP stapling, and set `server_tokens off;`. Target: Milestone 2 (M2).

---

### [FINDING-C3-SEC-04] Unauthenticated Public Exposure of `/downloads/` with Directory Auto-Indexing Enabled
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 28-39
  ```nginx
  28: location ^~ /downloads/ {
  ...
  37:   alias /shared/;
  38:   autoindex on;
  39:   autoindex_exact_size off;
  ```
- **Limitation / Vulnerability Description**: The `/downloads/` location maps directly to the host `/shared/` folder with `autoindex on;` without requiring any user authentication. Because all student instances share this folder, any unauthenticated client can enumerate and download every student's saved Packet Tracer network topologies, assignment files, and credential notes.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  curl -k https://localhost/downloads/
  # Output: HTML directory listing of all files across all user containers.
  ```
- **Current Operational Impact**: Severity: HIGH. Violates student privacy and academic integrity; enables trivial bulk exfiltration of coursework.
- **Recommended Hardening Action & Target Milestone**: Remove `autoindex on;`. Route file downloads through authenticated application endpoints or secure internal Nginx redirects (`X-Accel-Redirect`). Target: Milestone 2 (M2).

---

### [FINDING-C3-SEC-05] Unrestricted Access to Management Port 5000 Without GeoIP or Perimeter Controls
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 96-130
  ```nginx
  96: server {
  97:     listen 5000 ssl;
  98:     http2 on;
  99:     server_name localhost;
  ...
  113:    location / {
  114:        set $pt_mgmt_upstream http://pt-management:5000;
  115:        proxy_pass $pt_mgmt_upstream;
  ```
- **Limitation / Vulnerability Description**: Port 5000 exposes the administrative Flask interface. Unlike the main web server on port 443, port 5000 omits all GeoIP checking, rate limiting, and access control blocks.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -A 20 "server.*5000" ptweb-vnc/pt-nginx/conf/ptweb.conf | grep -E "allowed_country|limit_req"
  # Output: (Empty; no filtering rules present)
  ```
- **Current Operational Impact**: Severity: HIGH. Direct exposure of administrative login and REST APIs to external brute-force attacks.
- **Recommended Hardening Action & Target Milestone**: Apply rate limiting (`limit_req`), GeoIP filtering, and IP whitelisting to port 5000. Target: Milestone 2 (M2).

---

### 4.3 Performance and Resource Scaling (PERF)

### [FINDING-C3-PERF-01] Hardcoded Unconditional `Connection "upgrade"` Breaking HTTP/1.1 Keepalive
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 70-74
  ```nginx
  70:     # WebSocket support for Guacamole tunneling
  71:     proxy_http_version 1.1;
  72:     proxy_set_header Upgrade $http_upgrade;
  73:     proxy_set_header Connection "upgrade";
  ```
- **Limitation / Vulnerability Description**: The `Connection "upgrade"` header is hardcoded unconditionally. When standard HTTP/1.1 requests arrive (where `$http_upgrade` is empty), Nginx sends `Connection: upgrade` with an empty `Upgrade` header to upstream Tomcat. This violates RFC 7230 and terminates HTTP keepalive connections.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  curl -k -v -H "Upgrade:" https://localhost/guacamole/ 2>&1 | grep -i "connection"
  # Upstream receives malformed hop-by-hop upgrade headers on plain requests.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Premature socket teardowns and increased TCP/TLS connection handshake overhead between Nginx and Tomcat.
- **Recommended Hardening Action & Target Milestone**: Implement standard Nginx connection upgrade mapping: `map $http_upgrade $connection_upgrade { default upgrade; '' close; }`. Target: Milestone 2 (M2).

---

### [FINDING-C3-PERF-02] Missing TLS Session Caching and Session Tickets Causing Handshake Overhead
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 20-25 and 100-105
- **Limitation / Vulnerability Description**: Neither server block configures `ssl_session_cache` or `ssl_session_timeout`. Every HTTPS connection or asset request forces a full cryptographic TLS handshake.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "ssl_session" ptweb-vnc/pt-nginx/conf/
  # Output: (Empty)
  ```
- **Current Operational Impact**: Severity: LOW. Unnecessary CPU overhead on the edge gateway during initial lab session connections.
- **Recommended Hardening Action & Target Milestone**: Configure `ssl_session_cache shared:SSL:10m; ssl_session_timeout 1d; ssl_session_tickets off;`. Target: Milestone 2 (M2).

---

### 4.4 High Availability and Reliability (HA)

### [FINDING-C3-HA-01] Inappropriate Proxy Read Timeouts Leading to Abrupt Session Terminations
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 79-80 and 123-124
  ```nginx
  79: proxy_send_timeout 90;
  80: proxy_read_timeout 90;
  ```
- **Limitation / Vulnerability Description**: The proxy read timeout is set to 90 seconds. While active Guacamole tunnels transmit periodic ping/pong frames, temporary network hiccups or student pauses on passive documentation screens cause Nginx to abruptly close the proxy tunnel with HTTP 504.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "proxy_read_timeout" ptweb-vnc/pt-nginx/conf/ptweb.conf
  # Output: Lines 80 and 124 show 90 seconds.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Frustrating session disconnects during student lab pauses.
- **Recommended Hardening Action & Target Milestone**: Extend `proxy_read_timeout` to `3600s` for long-lived laboratory sessions. Target: Milestone 2 (M2).

---

### [FINDING-C3-HA-02] "If is Evil" Nginx Anti-Pattern in Dynamic GeoIP Location Blocks
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Code Reference**: Lines 30-36, 45-51, 57-63
  ```nginx
  30: if ($remote_addr ~ ^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)|86.50.84.227) {
  31:   set $allowed_country 1;
  32:   set $blocked_country 0;
  33: }
  34: if ($allowed_country = 0) { return 444; }
  ```
- **Limitation / Vulnerability Description**: Using multiple `if` statements inside `location` blocks is a well-documented anti-pattern in Nginx ("If is Evil"). In Nginx's declarative request processing model, evaluating nested conditions within locations can cause unexpected routing jumps, bypass `proxy_pass` blocks, and corrupt internal request state.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n -C 2 "if (\$allowed_country" ptweb-vnc/pt-nginx/conf/ptweb.conf
  # Multiple conditional blocks embedded within location contexts.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Risk of unpredictable request routing and silent configuration failures.
- **Recommended Hardening Action & Target Milestone**: Migrate all IP and country evaluation into top-level `geo` and `map` blocks outside location handlers. Target: Milestone 2 (M2).

---

### 4.5 Usability (USE)

### [FINDING-C3-USE-01] Routing Conflict Swallowing Static Assets and Web Portal `index.html`
- **Target File(s)**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`, `ptweb-vnc/pt-nginx/www/index.html`
- **Code Reference**: `ptweb.conf` lines 56-83
  ```nginx
  56: # Root location - proxy Guacamole at /
  57: location / {
  ...
  82:   proxy_pass http://pt-guacamole:8080/guacamole/;
  ```
- **Limitation / Vulnerability Description**: `ptweb-vnc/pt-nginx/www/index.html` contains an intended web portal page embedding Guacamole inside an iframe with custom banners. However, in `ptweb.conf`, `location /` directly proxies all root traffic to `http://pt-guacamole:8080/guacamole/`. Consequently, `index.html` and static assets in `/usr/share/nginx/html` (`favicon-32x32.png`, `apple-touch-icon.png`, `site.webmanifest`) are never served and return 404 from upstream Guacamole.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  curl -k -I https://localhost/favicon-32x32.png
  # Output: HTTP 404 (Proxied to Guacamole instead of served from static web root)
  ```
- **Current Operational Impact**: Severity: LOW. Custom branding, portal layout, and browser favicons fail to display.
- **Recommended Hardening Action & Target Milestone**: Define dedicated static location blocks (`location = /favicon.ico`, `location /static/`) with explicit `root` directives. Target: Milestone 2 (M2).

---

### 4.6 Maintainability (MAINT)

### [FINDING-C3-MAINT-01] Exposed PHP Scripts (`bulk-user-api.php`, `test.php`) Leaking Admin and DB Credentials
- **Target File(s)**: `ptweb-vnc/pt-nginx/www/bulk-user-api.php`, `ptweb-vnc/pt-nginx/www/test.php`
- **Code Reference**: `bulk-user-api.php` lines 21-22 and lines 31-34
  ```php
  21: $ADMIN_USER = 'admin';
  22: $ADMIN_PASS = 'admin123';
  ...
  31: $DB_HOST = 'mariadb';
  32: $DB_USER = 'ptdbuser';
  33: $DB_PASS = 'ptdbpass';
  34: $DB_NAME = 'guacamole_db';
  ```
- **Limitation / Vulnerability Description**: `bulk-user-api.php` is located in `/usr/share/nginx/html`. Because Nginx is compiled without PHP FastCGI support, requesting `/bulk-user-api.php` causes Nginx to serve the PHP file as static text, publicly exposing administrative credentials.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  cat ptweb-vnc/pt-nginx/www/bulk-user-api.php | grep -E "ADMIN_PASS|DB_PASS"
  # Verbatim plain-text credentials found in web root.
  ```
- **Current Operational Impact**: Severity: HIGH. Critical credential leakage to anyone scanning the web server.
- **Recommended Hardening Action & Target Milestone**: Delete legacy PHP scripts and add Nginx rule `location ~ \.(php|sh|sql|bak)$ { deny all; }`. Target: Milestone 2 (M2).

---

### [FINDING-C3-MAINT-02] Proliferation of Unmanaged Backup Configuration Files (`.bak.*`) in Repository
- **Target File(s)**: `ptweb-vnc/pt-nginx/`, `ptweb-vnc/pt-nginx/conf/`
- **Code Reference**: Git repository status
- **Limitation / Vulnerability Description**: `generate-nginx-conf.sh` creates timestamped `.bak.<timestamp>` files on every execution. Over 60 stale backup files are tracked in the Git repository.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  find ptweb-vnc/pt-nginx/ -name "*.bak.*" | wc -l
  # Output: 64 backup files
  ```
- **Current Operational Impact**: Severity: LOW. Repository bloat and confusion over authoritative configuration files.
- **Recommended Hardening Action & Target Milestone**: Purge tracked backup files from Git and add `*.bak.*` to `.gitignore`. Target: Milestone 2 (M2).

---

## 5. Component 4 Audit: Flask/Gunicorn Management Application

### 5.1 Component Overview
Component 4 is the management service located in `pt-management/`. Built with Python 3.11, Flask 3.0, and Gunicorn 21.2, it handles user authentication, bulk student provisioning, container lifecycle management, `.env` parameter updates, and shared workspace file operations.

---

### 5.2 Security and Hardening (SEC)

### [FINDING-C4-SEC-01] Unrestricted Host Takeover via Direct Docker Socket Mount and Root Container Execution
- **Target File(s)**: `deploy-full.sh`, `ptweb-vnc/docker-compose.yml`, `pt-management/Dockerfile`
- **Code Reference**: `deploy-full.sh` line 113; `docker-compose.yml` line 75; `Dockerfile` lines 1-40
  ```yaml
  volumes:
    - /var/run/docker.sock:/var/run/docker.sock
    - ./shared:/shared
    - ../.env:/app/.env
    - ..:/project
  ```
- **Limitation / Vulnerability Description**: The `pt-management` container runs as `root` (no `USER` directive in `Dockerfile`) and mounts the host Docker Unix domain socket (`/var/run/docker.sock`) directly. Anyone with execution privileges in `pt-management` has full root control over the host Docker daemon.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec pt-management whoami
  # Output: root
  docker inspect pt-management --format '{{range .Mounts}}{{if eq .Destination "/var/run/docker.sock"}}{{.Source}}{{end}}{{end}}'
  # Output: /var/run/docker.sock
  ```
- **Current Operational Impact**: Severity: CRITICAL. Combined with Finding C4-SEC-02, an external unauthenticated attacker can create containers with host root filesystem mounts (`-v /:/host`), resulting in immediate, total root takeover of the host server.
- **Recommended Hardening Action & Target Milestone**: Replace direct socket mount with a restricted `docker-socket-proxy` container exposing only necessary endpoints. Run `pt-management` as an unprivileged user (`USER appuser`). Target: Milestone 2 (M2).

---

### [FINDING-C4-SEC-02] Unauthenticated Endpoint `POST /api/containers` Allowing Arbitrary Container Spawning
- **Target File(s)**: `pt-management/app.py`
- **Code Reference**: Lines 100-101
  ```python
  100: if request.path.startswith('/api/containers') and request.method == 'POST':
  101:     return  # Skip auth
  ```
- **Limitation / Vulnerability Description**: In `app.py`, the authentication middleware explicitly bypasses authentication for all `POST` requests to `/api/containers`. Any network client can submit JSON payloads to provision new containers without providing credentials.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n -A 2 "api/containers.*POST" pt-management/app.py
  # Confirms unconditional auth skip.
  ```
- **Current Operational Impact**: Severity: CRITICAL. Unauthenticated remote denial of service and host compromise via uncontrolled container creation.
- **Recommended Hardening Action & Target Milestone**: Remove the auth skip. Enforce strict session token or API key authentication on `/api/containers`. Target: Milestone 2 (M2).

---

### [FINDING-C4-SEC-03] Spoofable IP-Based Authentication Bypass via Trusted `ProxyFix` Headers
- **Target File(s)**: `pt-management/app.py`, `pt-management/ptmanagement/api/routes.py`
- **Code Reference**: `app.py` lines 106-133; line 33
  ```python
  33: app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=0)
  ...
  106: client_ip = request.remote_addr
  107: is_internal = (
  108:     client_ip in ['127.0.0.1', '::1', 'localhost'] or 
  109:     client_ip.startswith('172.') or 
  110:     client_ip.startswith('10.')
  111: )
  112: if is_internal:
  113:     return  # Allow internal requests
  ```
- **Limitation / Vulnerability Description**: `app.py` permits bulk user creation, bulk user deletion, and single user deletion without authentication if `is_internal` is true. Because `ProxyFix` trusts the first `X-Forwarded-For` header, any external client sending `X-Forwarded-For: 10.0.0.1` causes `request.remote_addr` to become `10.0.0.1`, completely bypassing authentication. Furthermore, any client connecting from within Docker naturally has an IP starting with `172.`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  curl -k -H "X-Forwarded-For: 10.0.0.1" -X POST https://localhost:5000/api/users/bulk/delete
  # Bypasses auth check and enters route handler.
  ```
- **Current Operational Impact**: Severity: CRITICAL. Unauthenticated remote attackers can bulk delete all students and modify accounts.
- **Recommended Hardening Action & Target Milestone**: Remove all IP-based authentication bypasses. Require cryptographic session tokens or pre-shared internal API keys. Target: Milestone 2 (M2).

---

### [FINDING-C4-SEC-04] Hardcoded `SECRET_KEY` and Static `PTADMIN_PASSWORD` Fallback (`IlovePT`)
- **Target File(s)**: `pt-management/app.py`, `pt-management/ptmanagement/api/auth.py`
- **Code Reference**: `app.py` line 37; `auth.py` lines 181-185
  ```python
  app.py:37:
  app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-change-in-production')
  auth.py:181:
  ptadmin_password = os.environ.get('PTADMIN_PASSWORD', 'IlovePT')
  ```
- **Limitation / Vulnerability Description**: If `SECRET_KEY` is omitted from `.env`, Flask signs session cookies with the public static string `'dev-key-change-in-production'`. Any attacker can forge valid admin session cookies. Similarly, `auth.py` allows admin authentication with `'IlovePT'`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "dev-key-change" pt-management/app.py
  # Confirms hardcoded secret key fallback.
  ```
- **Current Operational Impact**: Severity: HIGH. Trivial administrative session forgery and credential brute-force bypass.
- **Recommended Hardening Action & Target Milestone**: Refuse to boot in production if `SECRET_KEY` is default or missing. Generate cryptographic random keys dynamically. Target: Milestone 2 (M2).

---

### [FINDING-C4-SEC-05] Broken Authorization in `env_routes.py` (`require_admin` Stub)
- **Target File(s)**: `pt-management/ptmanagement/api/env_routes.py`
- **Code Reference**: Lines 18-26
  ```python
  18: def require_admin(f):
  19:     """Decorator to require admin authentication"""
  20:     @wraps(f)
  21:     def decorated_function(*args, **kwargs):
  22:         if 'user' not in session:
  23:             return jsonify({'success': False, 'message': 'Unauthorized'}), 401
  24:         # Note: In production, also check if user is admin
  25:         return f(*args, **kwargs)
  26:     return decorated_function
  ```
- **Limitation / Vulnerability Description**: The `require_admin` decorator verifies only that `'user'` is present in `session`. It contains a comment `# Note: In production, also check if user is admin`, but never checks user privileges.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n -A 6 "def require_admin" pt-management/ptmanagement/api/env_routes.py
  # Confirms unverified authorization stub.
  ```
- **Current Operational Impact**: Severity: HIGH. Any authenticated student can view the raw `.env` file, modify Nginx configuration, and reboot Nginx containers.
- **Recommended Hardening Action & Target Milestone**: Integrate `is_user_admin(session['user'])` check into `require_admin`. Target: Milestone 2 (M2).

---

### [FINDING-C4-SEC-06] Shared World-Writable Folder Mount (`/shared`) Lacking Multi-Tenant Isolation
- **Target File(s)**: `deploy.sh`, `deploy-full.sh`, `pt-management/ptmanagement/api/file_manager.py`
- **Code Reference**: `deploy.sh` line 201 (`chmod 777 "${WORKDIR}/shared"`); `container.py` line 363
- **Limitation / Vulnerability Description**: All containers mount the identical host folder `/shared`. There is zero tenant segregation. Any student can view, overwrite, or delete assignments created by other students.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker inspect ptvnc1 --format '{{range .Mounts}}{{if eq .Destination "/shared"}}{{.Source}}{{end}}{{end}}'
  docker inspect ptvnc2 --format '{{range .Mounts}}{{if eq .Destination "/shared"}}{{.Source}}{{end}}{{end}}'
  # Both inspect outputs resolve to identical host path /.../shared.
  ```
- **Current Operational Impact**: Severity: HIGH. Complete absence of multi-tenant data isolation; risk of accidental or malicious coursework sabotage.
- **Recommended Hardening Action & Target Milestone**: Isolate storage into `/shared/users/{username}/` with private per-container bind-mounts. Target: Milestone 2 (M2).

---

### 5.3 Performance and Resource Scaling (PERF)

### [FINDING-C4-PERF-01] Gunicorn Synchronous 2-Worker Architecture Starved by Blocking CLI Subprocesses
- **Target File(s)**: `pt-management/entrypoint.sh`, `pt-management/ptmanagement/api/routes.py`
- **Code Reference**: `entrypoint.sh` lines 50-54; `routes.py` lines 180-220
  ```bash
  entrypoint.sh:54: exec gunicorn --workers 2 --timeout 120 wsgi:app
  ```
- **Limitation / Vulnerability Description**: Gunicorn runs with only 2 synchronous worker processes. During bulk student creation, the worker invokes sequential synchronous Docker CLI commands (`docker run`, `docker exec`, `chmod`) taking 10-30 seconds per instance.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "workers" pt-management/entrypoint.sh
  # Confirms: --workers 2 (synchronous sync workers)
  ```
- **Current Operational Impact**: Severity: HIGH. Two concurrent administrative actions completely block both Gunicorn workers, causing all other API calls and web dashboard requests to hang and time out with HTTP 504.
- **Recommended Hardening Action & Target Milestone**: Migrate to an asynchronous worker model (e.g. `gthread` with background task queue like Celery or RQ) for heavy container provisioning tasks. Target: Milestone 3 (M3).

---

### [FINDING-C4-PERF-02] Database Connection Churn Without Connection Pooling
- **Target File(s)**: `pt-management/ptmanagement/db/connection.py`
- **Code Reference**: Lines 11-25
  ```python
  11: def get_db_connection():
  ...
  17:     connection = mysql.connector.connect(
  18:         host=os.environ.get('DB_HOST', 'guacamole-mariadb'),
  19:         user=os.environ.get('DB_USER', 'ptdbuser'),
  20:         password=os.environ.get('DB_PASS', 'ptdbpass'),
  21:         database=os.environ.get('DB_NAME', 'guacamole_db'),
  22:         raise_on_warnings=False,
  23:         autocommit=True
  24:     )
  25:     return connection
  ```
- **Limitation / Vulnerability Description**: `get_db_connection()` opens and closes a new TCP connection to MariaDB for every single query execution without connection pooling.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "MySQLConnectionPool" pt-management/
  # Output: (Empty; no pooling implemented)
  ```
- **Current Operational Impact**: Severity: MEDIUM. Severe socket churn, latency overhead, and risk of exhausting MariaDB `max_connections` during class logins.
- **Recommended Hardening Action & Target Milestone**: Implement `mysql.connector.pooling.MySQLConnectionPool`. Target: Milestone 2 (M2).

---

### 5.4 High Availability and Reliability (HA)

### [FINDING-C4-HA-01] Fatal SQL Bug in `delete_connection` Function Aborting Deletion Operations
- **Target File(s)**: `pt-management/ptmanagement/db/guacamole.py`
- **Code Reference**: Lines 660-664
  ```python
  660: # Delete user permissions for this connection
  661: execute_query(
  662:     "DELETE FROM guacamole_user_permission WHERE connection_id = %s",
  663:     (connection_id,)
  664: )
  ```
- **Limitation / Vulnerability Description**: In Guacamole's schema, `guacamole_user_permission` has columns `(entity_id, affected_user_id, permission)`. It has NO `connection_id` column (connection permissions reside in `guacamole_connection_permission`). Calling `delete_connection()` raises MySQL error 1054 (`Unknown column 'connection_id' in 'where clause'`), causing the transaction to abort and fail.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass guacamole_db -e "DESCRIBE guacamole_user_permission;"
  # Columns: entity_id, affected_user_id, permission (connection_id does not exist)
  ```
- **Current Operational Impact**: Severity: HIGH. Programmatic connection deletion via the web dashboard or API fails permanently, leaving orphaned connection records in Guacamole.
- **Recommended Hardening Action & Target Milestone**: Correct query to `DELETE FROM guacamole_connection_permission WHERE connection_id = %s`. Target: Milestone 2 (M2).

---

### [FINDING-C4-HA-02] Broken Authentication Check in `upload_routes.py` Rejecting SSL Certificate Uploads
- **Target File(s)**: `pt-management/ptmanagement/api/upload_routes.py`
- **Code Reference**: Lines 118, 151, 192
  ```python
  118: if 'user' not in request.environ.get('session', {}):
  119:     return jsonify({'success': False, 'message': 'Unauthorized'}), 401
  ```
- **Limitation / Vulnerability Description**: Flask sessions are managed by Flask's session interface and are not stored in WSGI `request.environ['session']`. `request.environ.get('session', {})` returns `{}`. Consequently, `'user' not in {}` is always `True`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "request.environ.get('session'" pt-management/ptmanagement/api/upload_routes.py
  # Confirms broken inspection across 3 endpoints.
  ```
- **Current Operational Impact**: Severity: HIGH. Legitimate authenticated administrators are permanently blocked from uploading SSL certificates or keys through the web dashboard.
- **Recommended Hardening Action & Target Milestone**: Replace `request.environ.get('session')` with Flask's native `session` object (`if 'user' not in session:`). Target: Milestone 2 (M2).

---

### [FINDING-C4-HA-03] Network Isolation Divergence Between Management Application and Guacamole Stack
- **Target File(s)**: `pt-management/ptmanagement/api/routes.py`, `deploy.sh`, `deploy-full.sh`
- **Code Reference**: `routes.py` lines 541-546
  ```python
  541: net_cmd = ['docker', 'network', 'connect', 'pt-stack', container_name]
  542: net_result = subprocess.run(net_cmd, capture_output=True, text=True, timeout=10)
  ```
- **Limitation / Vulnerability Description**: Containers provisioned via `deploy.sh` attach to `ptnet`. However, `routes.py` attempts to attach newly created containers to `pt-stack`. If deployed via `deploy.sh`, `pt-stack` does not exist or Guacamole is not attached to it, preventing `guacd` from resolving or connecting to the newly provisioned instances.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "pt-stack" pt-management/ptmanagement/api/routes.py
  # Shows hardcoded attachment to pt-stack instead of canonical ptnet.
  ```
- **Current Operational Impact**: Severity: HIGH. Instances created via the UI are unreachable by Guacamole, resulting in connection failure screens for students.
- **Recommended Hardening Action & Target Milestone**: Unify all container networking under a single canonical network model. Target: Milestone 2 (M2).

---

### 5.5 Usability (USE)

### [FINDING-C4-USE-01] User Session Terminations and UI Stalls on Provisioning Timeouts
- **Target File(s)**: `pt-management/ptmanagement/api/routes.py`, `pt-management/static/js/dashboard.js`
- **Code Reference**: Synchronous execution in `routes.py`
- **Limitation / Vulnerability Description**: When creating batches of 10+ student accounts, the browser holds an open HTTP connection for over 90 seconds. Nginx or the browser hits timeout limits, triggering error dialogs even while the backend continues creating containers.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  # Triggering bulk create of 15 instances causes HTTP 504 Gateway Timeout on UI.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Instructors believe provisioning failed and resubmit forms, spawning duplicate containers and thrashing system resources.
- **Recommended Hardening Action & Target Milestone**: Implement asynchronous task processing with progress bars and polling endpoints (`/api/tasks/<id>`). Target: Milestone 3 (M3).

---

### 5.6 Maintainability (MAINT)

### [FINDING-C4-MAINT-01] Hardcoded Host Drive Paths (`/run/media/kalpa/...`) in Application Code
- **Target File(s)**: `pt-management/ptmanagement/docker_mgmt/container.py`, `pt-management/ptmanagement/api/routes.py`
- **Code Reference**: `container.py` line 358; `routes.py` line 190
  ```python
  container.py:358:
  shared_path = shared_host_path_env if shared_host_path_env else '/run/media/kalpa/9530f1e7-4f57-4bf2-b7f2-b03a2b8d4111/PT DEv/PacketTracerWeb/shared'
  routes.py:190:
  '/run/media/kalpa/9530f1e7-4f57-4bf2-b7f2-b03a2b8d4111/PT DEv/PacketTracerWeb/CiscoPacketTracer.deb',
  ```
- **Limitation / Vulnerability Description**: Absolute paths from a specific developer's workstation external hard drive are hardcoded as fallbacks in core application logic.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "/run/media/kalpa" pt-management/
  # Confirmed in container.py and routes.py.
  ```
- **Current Operational Impact**: Severity: MEDIUM. On production servers, fallbacks point to non-existent directories, causing volume mount and package resolution failures.
- **Recommended Hardening Action & Target Milestone**: Remove workstation paths; enforce configuration strictly via environment variables with relative repository defaults. Target: Milestone 2 (M2).

---

### [FINDING-C4-MAINT-02] Database Environment Variable Name Mismatches (`DB_PASS` vs `DB_PASSWORD`)
- **Target File(s)**: `pt-management/ptmanagement/db/connection.py`, `pt-management/ptmanagement/api/env_config.py`
- **Code Reference**: `connection.py` line 20; `env_config.py` line 579
  ```python
  connection.py:20: password=os.environ.get('DB_PASS', 'ptdbpass'),
  env_config.py:579: if key == 'GUAC_DB_PASSWORD':
  ```
- **Limitation / Vulnerability Description**: Three different variable names (`DB_PASS`, `DB_PASSWORD`, `GUAC_DB_PASSWORD`) are used to represent the MariaDB database password across different files in the management service.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "DB_PASS" pt-management/
  # Shows conflicting variable name lookups.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Configuration changes made in `.env` are inconsistently applied across submodules.
- **Recommended Hardening Action & Target Milestone**: Consolidate database environment variables to `DB_PASSWORD`. Target: Milestone 2 (M2).

---

### [FINDING-C4-MAINT-03] Inconsistent Container Creation Implementations (CLI Subprocess vs Custom Socket Client)
- **Target File(s)**: `pt-management/ptmanagement/docker_mgmt/container.py`, `pt-management/ptmanagement/api/routes.py`
- **Code Reference**: `container.py` lines 14-133 (`DockerSocketClient`); `routes.py` line 206 (`subprocess.run(['docker', 'run', ...])`)
- **Limitation / Vulnerability Description**: Two completely separate, conflicting container provisioning engines exist: a custom raw Unix domain socket HTTP client in `container.py`, and shell CLI subprocess calls in `routes.py`. Meanwhile, the official `docker` Python SDK is pinned in `requirements.txt` but never used.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep "import docker" pt-management/ -R
  # Output: (Empty; official SDK never imported)
  ```
- **Current Operational Impact**: Severity: MEDIUM. Code bloat, duplicated bugs, and divergence in container configurations.
- **Recommended Hardening Action & Target Milestone**: Replace both custom socket and subprocess implementations with the official `docker` Python SDK. Target: Milestone 2 (M2).

---

## 6. Component 5 Audit: Deployment Orchestration & Verification Harness

### 6.1 Component Overview
Component 5 covers deployment scripts (`deploy.sh`, `deploy-full.sh`, `add-instance.sh`, `remove-instance.sh`), container definitions (`ptweb-vnc/docker-compose.yml`), cleanup scripts (`Scripts/cleanup-all.sh`), and the verification harness (`health_check.sh`).

---

### 6.2 Security and Hardening (SEC)

### [FINDING-C5-SEC-01] Missing Image Digest Verification and Unencrypted HTTP Package Downloads
- **Target File(s)**: `ptweb-vnc/Dockerfile`, `ptweb-vnc/pt-nginx/Dockerfile`
- **Code Reference**: `ptweb-vnc/Dockerfile` lines 29, 39; `pt-nginx/Dockerfile` line 20
  ```dockerfile
  ptweb-vnc/Dockerfile:29: wget -q https://github.com/TurboVNC/turbovnc/releases/download/3.3/turbovnc_3.3_amd64.deb
  pt-nginx/Dockerfile:20: wget http://nginx.org/download/nginx-${NGINX_VERSION}.tar.gz
  ```
- **Limitation / Vulnerability Description**: Binaries and source archives are downloaded during container builds without SHA256 checksum validation. Furthermore, Nginx source tarballs are downloaded over unencrypted HTTP.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep "wget" ptweb-vnc/Dockerfile ptweb-vnc/pt-nginx/Dockerfile
  # Confirms unverified downloads over HTTP and HTTPS without checksum checks.
  ```
- **Current Operational Impact**: Severity: HIGH. Vulnerable to MITM tampering, compromised upstream release binaries, and supply-chain attacks.
- **Recommended Hardening Action & Target Milestone**: Enforce SHA256 verification on all external binaries and download solely over HTTPS. Target: Milestone 2 (M2).

---

### [FINDING-C5-SEC-02] Destructive Host-Wide Docker Engine Deletion in `cleanup-all.sh`
- **Target File(s)**: `Scripts/cleanup-all.sh`
- **Code Reference**: Lines 48, 58, 68, 78, 87
  ```bash
  48: docker stop $(docker ps -q) 2>/dev/null || true
  58: docker rm $(docker ps -aq) 2>/dev/null || true
  68: docker rmi $(docker images -q) 2>/dev/null || true
  78: docker volume rm $(docker volume ls -q) 2>/dev/null || true
  87: docker system prune -f --volumes 2>/dev/null || true
  ```
- **Limitation / Vulnerability Description**: `cleanup-all.sh` executes blanket cleanup commands without scoping to project labels or container name prefixes.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "docker volume rm" Scripts/cleanup-all.sh
  # Confirms un-scoped removal of all host volumes.
  ```
- **Current Operational Impact**: Severity: CRITICAL. Running this script irrevocably destroys all containers, images, and named volumes across the entire host machine, annihilating unrelated databases and applications.
- **Recommended Hardening Action & Target Milestone**: Scope all deletion commands strictly to project resources (`--filter label=com.docker.compose.project=ptweb`). Target: Milestone 2 (M2).

---

### 6.3 Performance and Resource Scaling (PERF)

### [FINDING-C5-PERF-01] Excessive 115-Second Hardcoded Startup Sleep Delays Without Polling
- **Target File(s)**: `deploy.sh`, `deploy-full.sh`
- **Code Reference**: `deploy.sh` lines 197, 249, 258; `deploy-full.sh` line 88
  ```bash
  deploy.sh:197: sleep 10
  deploy.sh:249: sleep 20
  deploy.sh:258: sleep 20
  deploy-full.sh:88: sleep 60
  ```
- **Limitation / Vulnerability Description**: Orchestration scripts rely on cumulative hardcoded sleep intervals totaling 115+ seconds instead of polling readiness probes (e.g. `mariadb-admin ping`, Guacamole HTTP GET).
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "sleep " deploy.sh deploy-full.sh
  # Lists 115+ seconds of unconditional sleeps.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Slows down deployments on fast hardware, while still failing with race conditions on slow disks if MariaDB takes longer than 20 seconds to initialize.
- **Recommended Hardening Action & Target Milestone**: Replace arbitrary sleep delays with active health probe loops. Target: Milestone 2 (M2).

---

### [FINDING-C5-PERF-02] Arbitrary and Inconsistent Resource Limits Across Provisioning Interfaces
- **Target File(s)**: `deploy.sh`, `pt-management/ptmanagement/docker_mgmt/container.py`, `pt-management/ptmanagement/api/routes.py`, `ptweb-vnc/docker-compose.yml`
- **Code Reference**: Conflicting resource flags across codebase:
  - `deploy.sh` line 231: `--cpus=0.5 -m 2G`
  - `container.py` line 333: `"Memory": 536870912` (512MB), no CPU limit
  - `routes.py` line 206: `--cpus 0.1 -m 1G`
  - `docker-compose.yml`: No CPU or memory limits configured
- **Limitation / Vulnerability Description**: Container resource allocations vary 5-fold depending on which script or UI created them.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "\-m " deploy.sh pt-management/
  # Reveals 512MB, 1GB, and 2GB allocations.
  ```
- **Current Operational Impact**: Severity: HIGH. 512MB instances crash immediately under Packet Tracer WebEngine loads; 0.1 CPU allocations result in unusable desktop lag.
- **Recommended Hardening Action & Target Milestone**: Standardize instance sizing to 1.0 CPU, 2.0GB RAM, 512MB swap. Target: Milestone 2 (M2).

---

### [FINDING-C5-PERF-03] Dangerous Flag Usage: `--kernel-memory` Deprecation and `--oom-kill-disable`
- **Target File(s)**: `ptweb-vnc/scripts/start-full-stack.sh`, `tune_ptvnc.sh`
- **Code Reference**: `start-full-stack.sh` line 36; `tune_ptvnc.sh` line 11
  ```bash
  start-full-stack.sh:36: --kernel-memory 128M --oom-kill-disable
  tune_ptvnc.sh:11: docker update --memory "$mem" --memory-swap "$mem" ...
  ```
- **Limitation / Vulnerability Description**:
  1. `--kernel-memory` is deprecated on modern cgroups v2.
  2. Disabling the OOM killer (`--oom-kill-disable`) without strict memory reservations can freeze the host Linux kernel.
  3. Setting `--memory-swap` equal to `--memory` disables swap entirely, contrary to `tune_ptvnc.sh` documentation.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -E "kernel-memory|oom-kill-disable" ptweb-vnc/scripts/start-full-stack.sh
  # Confirmed dangerous runtime flags.
  ```
- **Current Operational Impact**: Severity: MEDIUM. Risk of host kernel hang under memory exhaustion.
- **Recommended Hardening Action & Target Milestone**: Purge deprecated flags and configure standard memory + swap ratios. Target: Milestone 2 (M2).

---

### 6.4 High Availability and Reliability (HA)

### [FINDING-C5-HA-01] Complete Absence of Docker `HEALTHCHECK` Directives Across All Services
- **Target File(s)**: `ptweb-vnc/Dockerfile`, `ptweb-vnc/pt-nginx/Dockerfile`, `pt-management/Dockerfile`, `ptweb-vnc/docker-compose.yml`
- **Code Reference**: All Dockerfiles and Compose files
- **Limitation / Vulnerability Description**: Zero `HEALTHCHECK` directives exist anywhere in the repository. Docker daemon and compose orchestrators have no mechanism to evaluate whether services are functional or hung.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -rn "HEALTHCHECK" ptweb-vnc/ pt-management/
  # Output: (Empty across all Dockerfiles)
  ```
- **Current Operational Impact**: Severity: HIGH. If an internal service (e.g. MariaDB or guacd) crashes, Docker reports the container as healthy/running, preventing automated recovery.
- **Recommended Hardening Action & Target Milestone**: Define robust `HEALTHCHECK` instructions in all Dockerfiles and compose services. Target: Milestone 2 (M2).

---

### [FINDING-C5-HA-02] Non-Supervised Daemon Loop in `start-session` Masking Container Crashes
- **Target File(s)**: `ptweb-vnc/customizations/start-session`
- **Code Reference**: Lines 146-147
  ```bash
  146: # Keep container alive
  147: while true; do sleep 3600; done
  ```
- **Limitation / Vulnerability Description**: At the end of `start-session`, the script executes an infinite sleep loop. If TurboVNC, XFCE4, or Packet Tracer crashes, the container remains in status `Up` because PID 1 is sleeping. Docker restart policies (`unless-stopped`) never trigger.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  docker exec ptvnc1 killall Xvnc
  docker ps --filter "name=ptvnc1"
  # Container remains "Up", but VNC server is dead and unreachable.
  ```
- **Current Operational Impact**: Severity: HIGH. Containers become persistent "zombie" instances that reject connections until an administrator manually restarts them.
- **Recommended Hardening Action & Target Milestone**: Implement a process supervisor (`supervisord` or `s6-overlay`) that exits the container or restarts services if core daemons terminate. Target: Milestone 2 (M2).

---

### [FINDING-C5-HA-03] Absence of Database Backup, Snapshotting, and Disaster Recovery Tooling
- **Target File(s)**: Deployment and scripts directory
- **Code Reference**: Entire repository
- **Limitation / Vulnerability Description**: No automated database dump scripts, backup rotation policies, or disaster recovery procedures exist.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  find . -name "*backup*"
  # Shows only configuration backup files, zero database backup scripts.
  ```
- **Current Operational Impact**: Severity: HIGH. System administrators cannot restore student lab state following hardware failure or accidental corruption.
- **Recommended Hardening Action & Target Milestone**: Implement automated `backup-db.sh` and `restore-db.sh` utility scripts with retention rotation. Target: Milestone 3 (M3).

---

### 6.5 Usability (USE)

### [FINDING-C5-USE-01] Fragile Scale-Out Script Requiring Exact Numerical Container Sequence
- **Target File(s)**: `add-instance.sh`, `deploy.sh`
- **Code Reference**: `add-instance.sh` lines 42-50; `deploy.sh` lines 11, 227
  ```bash
  42: # Get current highest instance number
  43: current_max=$(docker ps --format "table {{.Names}}" | grep "^ptvnc" | sed 's/ptvnc//' | sort -n | tail -1)
  44: if [[ -z "$current_max" ]]; then
  45:     current_max=0
  46: fi
  ...
  50: echo "Will create: ptvnc$((current_max+1)) to ptvnc$((current_max+instances_to_add))"
  ```
- **Limitation / Vulnerability Description**: While initial provisioning in `deploy.sh` uses a fixed `numofPT` loop index (lines 11, 227), `add-instance.sh` computes `current_max` by grepping active containers and extracting the highest numerical suffix (`tail -1`, lines 42-46). If intermediate instances are stopped or deleted out of sequence (e.g., `ptvnc2` terminated while `ptvnc3` remains), `add-instance.sh` appends after the maximum index rather than reclaiming gaps, causing sequence divergence from downstream indexing assumptions.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  sed -n '42,50p' add-instance.sh
  # Shows tail -1 max index calculation and unhandled gap detection.
  ```
- **Current Operational Impact**: Severity: LOW. Script failures during dynamic scaling operations.
- **Recommended Hardening Action & Target Milestone**: Migrate dynamic instance scaling to declarative Docker Compose profiles (`docker compose up --scale ptvnc=N`). Target: Milestone 3 (M3).

---

### 6.6 Maintainability (MAINT)

### [FINDING-C5-MAINT-01] Dual Orchestration Engine Divergence (`deploy.sh` vs `docker-compose.yml`)
- **Target File(s)**: `deploy.sh`, `ptweb-vnc/docker-compose.yml`
- **Code Reference**: Entire deployment pipeline
- **Limitation / Vulnerability Description**: The repository maintains two divergent deployment architectures: a procedural Docker CLI script (`deploy.sh`), and a declarative Docker Compose file (`docker-compose.yml`). The compose file omits desktop instances entirely and uses stock Nginx rather than custom `pt-nginx`.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  diff -u <(grep -E "image:" ptweb-vnc/docker-compose.yml) <(grep -E "docker run" deploy.sh)
  # Substantial architectural differences between the two definitions.
  ```
- **Current Operational Impact**: Severity: HIGH. High cognitive overhead, duplicated maintenance effort, and configuration drift.
- **Recommended Hardening Action & Target Milestone**: Establish Docker Compose v2 as the single canonical source of truth for the entire platform. Target: Milestone 3 (M3).

---

### [FINDING-C5-MAINT-02] Passive Verification in `health_check.sh` Hardcoding Database Secrets
- **Target File(s)**: `health_check.sh`
- **Code Reference**: Lines 128-138
  ```bash
  128: run_test "MariaDB is accessible" \
  129:     "docker exec guacamole-mariadb mariadb -uptdbuser -pptdbpass -e 'SELECT 1' > /dev/null"
  ```
- **Limitation / Vulnerability Description**: `health_check.sh` hardcodes credentials in plain text. Furthermore, it only executes read-only passive tests without providing remediation or recovery actions.
- **Empirical Evidence / Reproduction Command**:
  ```bash
  grep -n "pptdbpass" health_check.sh
  # Confirms hardcoded secrets in test runner.
  ```
- **Current Operational Impact**: Severity: LOW. Maintenance debt and security policy violation.
- **Recommended Hardening Action & Target Milestone**: Parameterize `health_check.sh` to read credentials from `.env` or Docker secrets. Target: Milestone 2 (M2).

---

### [FINDING-C5-MAINT-03] Broken Relative Script Invocations in `Scripts/` Subdirectory
- **Target File(s)**: `Scripts/test-geoip-blocking.sh`, `Scripts/cleanup-and-redeploy.sh`
- **Code Reference**: `Scripts/test-geoip-blocking.sh` line 14 (and lines 6-12); `cleanup-and-redeploy.sh` lines 20-30
- **Limitation / Vulnerability Description**: Scripts inside `Scripts/` (such as `test-geoip-blocking.sh`) reference configuration files assuming they are located within the current script directory (e.g. attempting to source `$WORKDIR/.env` after changing directory to `Scripts/`, where `.env` exists only in the parent project root).
- **Empirical Evidence / Reproduction Command**:
  ```bash
  cd Scripts && bash test-geoip-blocking.sh
  # Fails to load .env configuration due to local directory resolution.
  ```
- **Current Operational Impact**: Severity: LOW. Broken utility scripts for operators.
- **Recommended Hardening Action & Target Milestone**: Standardize script root resolution: `ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"`. Target: Milestone 2 (M2).

---

## 7. Summary Matrix & Cross-Cutting Analysis

### 7.1 Component vs. Operational Domain Risk Matrix

The matrix below quantifies the distribution and severity of all 62 findings across the system:

| Architectural Component | Security (SEC) | Performance (PERF) | Reliability (HA) | Usability (USE) | Maintainability (MAINT) | Total Findings |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Component 1**: PT Virtual Desktop (`ptweb-vnc`) | 2 (1H, 1M) | 3 (2H, 1M) | 3 (3H) | 2 (1M, 1L) | 2 (1M, 1L) | **12** |
| **Component 2**: Guacamole Gateway Stack | 2 (2H) | 2 (1H, 1M) | 3 (1C, 2H) | 2 (1H, 1M) | 2 (1M, 1L) | **11** |
| **Component 3**: Nginx Edge Gateway | 5 (5H) | 2 (1M, 1L) | 2 (2M) | 1 (1L) | 2 (1H, 1L) | **12** |
| **Component 4**: Flask/Gunicorn Management | 6 (3C, 3H) | 2 (1H, 1M) | 3 (3H) | 1 (1M) | 3 (3M) | **15** |
| **Component 5**: Deployment & Verification | 2 (1C, 1H) | 3 (1H, 2M) | 3 (3H) | 1 (1L) | 3 (1H, 2L) | **12** |
| **Total Findings by Domain** | **17** | **12** | **14** | **7** | **12** | **62** |

*Severity Breakdown*: **5 Critical (C)**, **35 High (H)**, **16 Medium (M)**, **6 Low (L)**.

---

### 7.2 Comprehensive Finding Index

| Finding ID | Component | Domain | Severity | Target File | Core Vulnerability / Limitation |
|---|:---:|:---:|:---:|---|---|
| `FINDING-C1-SEC-01` | C1 | SEC | HIGH | `start-session` | TurboVNC server launched with `-securitytypes none`. |
| `FINDING-C1-SEC-02` | C1 | SEC | MEDIUM | `deploy.sh` | Missing capability dropping (`--cap-drop=ALL`) and security profile boundaries. |
| `FINDING-C1-PERF-01` | C1 | PERF | HIGH | `start-session` | Dual concurrent X servers (`Xvfb :1` + `TurboVNC :2`) wasting ~208MB RAM. |
| `FINDING-C1-PERF-02` | C1 | PERF | HIGH | `deploy.sh` | Constrained 64MB `/dev/shm` starving QtWebEngine Chromium renderer. |
| `FINDING-C1-PERF-03` | C1 | PERF | MEDIUM | `deploy.sh` | Insufficient file descriptor (`1024`) and process (`2048`) ulimits. |
| `FINDING-C1-HA-01` | C1 | HA | HIGH | `Dockerfile` | PID 1 lacks subreaper; leaks defunct `[AppRun]` zombie processes. |
| `FINDING-C1-HA-02` | C1 | HA | HIGH | `runtime-install.sh` | Uncoordinated concurrent deb extraction on shared volume `pt_opt`. |
| `FINDING-C1-HA-03` | C1 | HA | HIGH | `pt-install.sh` | Missing AppImage detection causes false fatal error and launch abort. |
| `FINDING-C1-USE-01` | C1 | USE | MEDIUM | `xstartup` | TurboVNC bypasses user `xstartup`, disabling `autocutsel` clipboard bridge. |
| `FINDING-C1-USE-02` | C1 | USE | LOW | `Dockerfile` | Complete absence of PulseAudio virtual sound subsystem. |
| `FINDING-C1-MAINT-01` | C1 | MAINT | MEDIUM | `start-session` | Failed `su - ptuser` call in non-root context causes auth failure log spam. |
| `FINDING-C1-MAINT-02` | C1 | MAINT | LOW | `verify-rdp-deployment.sh` | Dead code and mismatched XRDP protocol test artifacts. |
| `FINDING-C2-SEC-01` | C2 | SEC | HIGH | `connection.py` | Hardcoded database credentials and `DB_PASS` vs `DB_PASSWORD` mismatch. |
| `FINDING-C2-SEC-02` | C2 | SEC | HIGH | `db-dump.sql` | Static 2020 password hash and hardcoded `IlovePT` fallback. |
| `FINDING-C2-PERF-01` | C2 | PERF | HIGH | `ptweb.conf` | Missing `proxy_buffering off;` causes Guacamole streaming lag. |
| `FINDING-C2-PERF-02` | C2 | PERF | MEDIUM | `generate-dynamic-connections.sh`| Missing Guacamole connection parameter tuning (`color-depth`, `cursor`). |
| `FINDING-C2-HA-01` | C2 | HA | CRITICAL | `docker-compose.yml` | Anonymous volume for MariaDB `/var/lib/mysql` causes permanent data loss on recreate. |
| `FINDING-C2-HA-02` | C2 | HA | HIGH | `generate-dynamic-connections.sh`| MariaDB `NULL` parent_id duplicates connections and breaks parameter mapping. |
| `FINDING-C2-HA-03` | C2 | HA | HIGH | `ptweb.conf` | Absence of Tomcat `RemoteIpValve` causes Nginx proxy IP ban lockouts. |
| `FINDING-C2-USE-01` | C2 | USE | HIGH | `remove-instance.sh` | Deprovisioning one container destroys guacd/guacamole, disconnecting all users. |
| `FINDING-C2-USE-02` | C2 | USE | MEDIUM | `generate-dynamic-connections.sh`| Duplicate connection tiles with missing parameters displayed in web UI. |
| `FINDING-C2-MAINT-01` | C2 | MAINT | MEDIUM | `docker-compose.yml` | Unpinned upstream container image tags (`mariadb:latest`, `guacd:latest`). |
| `FINDING-C2-MAINT-02` | C2 | MAINT | LOW | `guacamole.properties` | Orphan configuration file containing hardcoded bridge IP `172.17.0.5`. |
| `FINDING-C3-SEC-01` | C3 | SEC | HIGH | `Dockerfile` | Deprecated GeoIP1 format compiled; unverified download from `mailfud.org`. |
| `FINDING-C3-SEC-02` | C3 | SEC | HIGH | `nginx.conf` | Invalid country codes (`UK`, `SL`) and unanchored regex bypass vulnerability. |
| `FINDING-C3-SEC-03` | C3 | SEC | HIGH | `ptweb.conf` | Permissive TLS ciphers, missing OCSP stapling, absence of HSTS and security headers. |
| `FINDING-C3-SEC-04` | C3 | SEC | HIGH | `ptweb.conf` | Public exposure of `/downloads/` with unauthenticated directory listing. |
| `FINDING-C3-SEC-05` | C3 | SEC | HIGH | `ptweb.conf` | Management port 5000 directly exposed without GeoIP or perimeter rate limiting. |
| `FINDING-C3-PERF-01` | C3 | PERF | MEDIUM | `ptweb.conf` | Unconditional `Connection "upgrade"` breaks HTTP/1.1 persistent keepalive. |
| `FINDING-C3-PERF-02` | C3 | PERF | LOW | `ptweb.conf` | Absence of TLS session cache and session tickets increases handshake latency. |
| `FINDING-C3-HA-01` | C3 | HA | MEDIUM | `ptweb.conf` | Short 90s proxy read timeout triggers abrupt session disconnects during pauses. |
| `FINDING-C3-HA-02` | C3 | HA | MEDIUM | `ptweb.conf` | "If is Evil" anti-pattern in dynamic GeoIP location blocks. |
| `FINDING-C3-USE-01` | C3 | USE | LOW | `ptweb.conf` | Route `/` swallows static assets and intended portal `index.html`. |
| `FINDING-C3-MAINT-01` | C3 | MAINT | HIGH | `bulk-user-api.php` | Static text serving of PHP files discloses plaintext admin and DB passwords. |
| `FINDING-C3-MAINT-02` | C3 | MAINT | LOW | `pt-nginx/` | 64+ unmanaged `.bak.*` configuration backup files polluting repository. |
| `FINDING-C4-SEC-01` | C4 | SEC | CRITICAL | `deploy-full.sh` | Direct Docker socket mount (`docker.sock`) into container running as root. |
| `FINDING-C4-SEC-02` | C4 | SEC | CRITICAL | `app.py` | Unauthenticated endpoint `POST /api/containers` allows arbitrary container spawning. |
| `FINDING-C4-SEC-03` | C4 | SEC | CRITICAL | `app.py` | Spoofable IP bypass (`X-Forwarded-For: 10.0.0.1`) allows unauthenticated bulk operations. |
| `FINDING-C4-SEC-04` | C4 | SEC | HIGH | `app.py` | Hardcoded `SECRET_KEY` fallback allows session cookie forgery. |
| `FINDING-C4-SEC-05` | C4 | SEC | HIGH | `env_routes.py` | `require_admin` decorator stub allows any user to edit `.env` and reboot Nginx. |
| `FINDING-C4-SEC-06` | C4 | SEC | HIGH | `deploy.sh` | World-writable `/shared` folder mounted into all containers without isolation. |
| `FINDING-C4-PERF-01` | C4 | PERF | HIGH | `entrypoint.sh` | Synchronous 2-worker Gunicorn architecture starved by blocking CLI commands. |
| `FINDING-C4-PERF-02` | C4 | PERF | MEDIUM | `connection.py` | High database connection churn without connection pooling. |
| `FINDING-C4-HA-01` | C4 | HA | HIGH | `guacamole.py` | Fatal SQL error in `delete_connection` (non-existent `connection_id` column). |
| `FINDING-C4-HA-02` | C4 | HA | HIGH | `upload_routes.py` | Broken session check (`request.environ['session']`) blocks SSL certificate uploads. |
| `FINDING-C4-HA-03` | C4 | HA | HIGH | `routes.py` | Newly created containers attach to `pt-stack` instead of `ptnet`, breaking Guacamole. |
| `FINDING-C4-USE-01` | C4 | USE | MEDIUM | `routes.py` | Synchronous bulk provisioning causes UI timeouts and duplicate form submissions. |
| `FINDING-C4-MAINT-01` | C4 | MAINT | MEDIUM | `container.py` | Hardcoded developer external drive paths (`/run/media/kalpa/...`) in source. |
| `FINDING-C4-MAINT-02` | C4 | MAINT | MEDIUM | `connection.py` | Discrepancy between `DB_PASS`, `DB_PASSWORD`, and `GUAC_DB_PASSWORD`. |
| `FINDING-C4-MAINT-03` | C4 | MAINT | MEDIUM | `container.py` | Conflicting container creation logic (raw Unix socket vs CLI subprocess). |
| `FINDING-C5-SEC-01` | C5 | SEC | HIGH | `Dockerfile` | Missing SHA256 checksums and unencrypted HTTP package downloads. |
| `FINDING-C5-SEC-02` | C5 | SEC | CRITICAL | `cleanup-all.sh` | Destructive host-wide Docker deletion wiping all containers, images, and volumes. |
| `FINDING-C5-PERF-01` | C5 | PERF | MEDIUM | `deploy.sh` | Excessive 115-second hardcoded sleep timeouts without active readiness polling. |
| `FINDING-C5-PERF-02` | C5 | PERF | HIGH | `deploy.sh` | Resource limit discrepancy (0.1 vs 0.5 CPU, 512MB vs 2GB RAM) across provisioning. |
| `FINDING-C5-PERF-03` | C5 | PERF | MEDIUM | `tune_ptvnc.sh` | Dangerous flag usage: deprecated `--kernel-memory` and risky `--oom-kill-disable`. |
| `FINDING-C5-HA-01` | C5 | HA | HIGH | `docker-compose.yml` | Zero Docker `HEALTHCHECK` definitions across all repository containers. |
| `FINDING-C5-HA-02` | C5 | HA | HIGH | `start-session` | Unsupervised `while true; sleep 3600` masks crashes and prevents auto-restart. |
| `FINDING-C5-HA-03` | C5 | HA | HIGH | Deploy pipeline | Complete absence of database backup, snapshotting, and restore automation. |
| `FINDING-C5-USE-01` | C5 | USE | LOW | `add-instance.sh` | Fragile sequential index calculation clashing when containers are removed. |
| `FINDING-C5-MAINT-01` | C5 | MAINT | HIGH | `docker-compose.yml` | Architectural divergence between procedural `deploy.sh` and `docker-compose.yml`. |
| `FINDING-C5-MAINT-02` | C5 | MAINT | LOW | `health_check.sh` | Passive test harness hardcodes plain-text database secrets. |
| `FINDING-C5-MAINT-03` | C5 | MAINT | LOW | `Scripts/` | Broken relative path references inside utility scripts. |

---

### 7.3 Cross-Component Failure Cascades

The architectural audit reveals critical interdependencies where a defect in one component propagates catastrophic failures across the rest of the system:

```
[ CASCADE 1: UNRESTRICTED HOST TAKEOVER CASCADE ]
  Nginx Port 5000 Open ──► Unauthenticated POST /api/containers (C4-SEC-02)
                                 │
                                 ▼
                     Flask runs as root with /var/run/docker.sock mounted (C4-SEC-01)
                                 │
                                 ▼
                     Attacker spawns container with -v /:/host
                                 │
                                 ▼
                     COMPLETE ROOT COMPROMISE OF THE HOST OPERATING SYSTEM
```

```
[ CASCADE 2: DENIAL OF SERVICE VIA PROXY IP LOCKOUT ]
  Student fails login 5 times on web portal (C2-HA-03)
                                 │
                                 ▼
  Tomcat lacks RemoteIpValve; logs Nginx proxy IP (172.18.0.x)
                                 │
                                 ▼
  Guacamole BanningAuthenticationListener triggers 300s ban on Nginx IP
                                 │
                                 ▼
  ALL STUDENTS & INSTRUCTORS WORLDWIDE LOCKED OUT OF PLATFORM FOR 5 MINUTES
```

```
[ CASCADE 3: GUACAMOLE ROUTING & DATABASE CORRUPTION CASCADE ]
  deploy.sh runs generate-dynamic-connections.sh (C2-HA-02)
                                 │
                                 ▼
  SQL INSERT IGNORE creates duplicate pt01/pt02 rows (NULL parent_id)
                                 │
                                 ▼
  Subquery returns multiple rows; parameter insertion fails for duplicates
                                 │
                                 ▼
  UI displays broken connection tiles; management delete_connection SQL bug (C4-HA-01)
  prevents cleanup, causing permanent database inconsistency.
```

```
[ CASCADE 4: MULTI-TENANT ACADEMIC DATA EXFILTRATION CASCADE ]
  deploy.sh sets chmod 777 on /shared & mounts to all ptvnc containers (C4-SEC-06)
                                 │
                                 ▼
  Nginx ptweb.conf configures location /downloads/ with autoindex on (C3-SEC-04)
                                 │
                                 ▼
  Unauthenticated external client requests https://<host>/downloads/
                                 │
                                 ▼
  CONFIDENTIAL COURSEWORK & LAB SOLUTIONS EXFILTRATED FOR ALL STUDENTS
```

---

## 8. Prioritized Production Hardening Roadmap

To systematically resolve these 62 findings without service disruption, remediation is organized across four distinct phases aligned with project milestones:

### 8.1 Phase 1: Zero-Downtime Hotfixes & High-Risk Vulnerability Remediation (Milestone 2)
*Focus*: Immediate remediation of critical vulnerabilities, credential leaks, data loss hazards, and syntax bugs.
- **Security Hotfixes**:
  - Deploy `docker-socket-proxy` to restrict Docker API calls; remove direct socket mount from `pt-management` and run container as unprivileged user.
  - Eliminate unauthenticated bypass on `POST /api/containers` and remove spoofable IP checks in `app.py`.
  - Remove public `bulk-user-api.php` and `test.php` from web root; enforce Nginx block on sensitive file extensions (`.php`, `.sh`, `.sql`).
  - Disable `autoindex on;` in `/downloads/` and enforce authentication.
  - Enforce TurboVNC authentication (`-rfbauth`).
- **Data Persistence & Bug Fixes**:
  - Assign persistent named volume `mariadb_data:/var/lib/mysql` in MariaDB definitions.
  - Fix fatal SQL syntax bug in `delete_connection` (`guacamole_connection_permission`).
  - Fix broken session check in `upload_routes.py`.
  - Fix Guacamole duplicate connections query bug in `generate-dynamic-connections.sh`.
- **Streaming & Display Optimization**:
  - Add `proxy_buffering off;` and connection upgrade map to Nginx Guacamole proxy configuration.
  - Eliminate `Xvfb` from `start-session`; run TurboVNC directly on `:1`.
  - Increase container `/dev/shm` to 512MB and raise ulimits to 65536.

### 8.2 Phase 2: Architectural Decoupling & Container Hardening (Milestone 3)
*Focus*: Structural resilience, network isolation, multi-tenant workspace separation, and clean orchestration.
- **Container Hardening**:
  - Add `tini` init process to `ptweb-vnc/Dockerfile` to eliminate defunct zombie leaks.
  - Fix `pt-install.sh` to recognize AppImage executables and automate symlink generation.
  - Extract AppImage during build/init time to eliminate runtime extraction thrashing on `pt_opt`.
  - Apply `--cap-drop=ALL --cap-add=CHOWN,SETUID,SETGID` and `no-new-privileges` on all desktop instances.
- **Network Segmentation**:
  - Segment network into three isolated bridge networks: `frontend-net` (Nginx ↔ Guacamole/Management), `backend-net` (Guacamole ↔ MariaDB/guacd), and `vnc-net` (guacd ↔ ptvnc1..N).
  - Prevent user desktop containers from accessing the MariaDB database or management API.
- **Multi-Tenant Storage**:
  - Replace shared `/shared` mount with per-user isolated directories `/shared/users/{username}/`.
- **Modern GeoIP2 Migration**:
  - Recompile Nginx with `ngx_http_geoip2_module` using official MaxMind `.mmdb` databases.
  - Correct ISO codes (`GB`, `LK`) and replace `if` location blocks with top-level `geo`/`map` blocks.

### 8.3 Phase 3: High Availability, Observability & Operational Automation (Milestone 4)
*Focus*: Zero-disruption scaling, automated health probes, database backups, and concurrency scaling.
- **High Availability & Supervision**:
  - Refactor `remove-instance.sh` to deprovision single instances via SQL without restarting `guacd` or `guacamole`.
  - Implement container `HEALTHCHECK` instructions across all Dockerfiles and compose services.
  - Replace procedural `sleep` delays with active TCP/HTTP readiness polling probes.
  - Replace unsupervised `while-sleep` loop in `start-session` with a lightweight process supervisor.
- **Observability & Logging**:
  - Configure Docker daemon `json-file` log rotation (`max-size: 50m`, `max-file: 3`) across all containers.
  - Implement structured audit logging for administrative actions in `pt-management`.
- **Disaster Recovery**:
  - Implement automated daily database backup script (`scripts/backup-db.sh`) with gzip compression and 7-day retention rotation.
  - Rewrite `cleanup-all.sh` to safely scope deletion operations to project labels.
- **Management Concurrency**:
  - Transition Gunicorn to asynchronous threaded workers with background task execution for bulk provisioning.

### 8.4 Phase 4: Final Verification & Gate Validation (Milestone 5)
*Focus*: End-to-end verification, automated compliance testing, and stress testing.
- Execute full opaque-box verification test suite across Tiers 1-4.
- Conduct adversarial penetration testing against edge perimeter, API authentication, and container isolation boundaries.
- Verify zero regression across existing student laboratory workflows.

---

## 9. Conclusion & Baseline Assessment Attestation

This comprehensive baseline assessment verifies that while PacketTracerWeb provides an innovative foundation for remote network simulation, its existing deployment scripts, container definitions, and application logic contain severe architectural vulnerabilities and operational debt. 

By categorizing and documenting these **62 specific findings**, this report establishes the definitive technical evidence required to execute the Production Hardening Project. Implementing the phased remediation roadmap will transform PacketTracerWeb from an experimental prototype into a resilient, secure, and enterprise-grade multi-tenant platform.

---
*End of Document `docs/proposals/01_system_assessment.md`*
