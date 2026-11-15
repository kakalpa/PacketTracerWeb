"""
Independent Test Fixtures and Synthetic Proposal Generator for Self-Testing.
Generates compliant and faulty mock proposal Markdown documents for test harness validation.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import List

_CREATED_FILES: List[str] = []


def create_synthetic_proposal(mode: str = "valid") -> str:
    """
    Creates a temporary synthetic proposal document according to the specified mode:
      - 'valid': Fully compliant with Tier 1, 2, 3, and 4 requirements.
      - 'missing_tier3': Omits Nginx proxy buffering and network unification.
      - 'missing_tier4': Omits Phase 3 scaling and rollback procedures.
    Returns the absolute path to the generated file.
    """
    fd, path = tempfile.mkstemp(prefix=f"synthetic_proposal_{mode}_", suffix=".md")
    os.close(fd)
    _CREATED_FILES.append(path)

    content = _generate_content(mode)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

    return path


def cleanup_synthetic_proposals() -> None:
    """Removes all temporary synthetic proposal files created during testing."""
    global _CREATED_FILES
    for path in _CREATED_FILES:
        try:
            p = Path(path)
            if p.is_file():
                p.unlink()
        except OSError:
            pass
    _CREATED_FILES = []


def _generate_content(mode: str) -> str:
    include_tier3_buffering = (mode != "missing_tier3")
    include_tier4_phase3 = (mode != "missing_tier4")

    if include_tier3_buffering:
        buffering_snippet = """
```nginx
# Low-Latency Guacamole WebSocket Tunnel Configuration
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

location /guacamole/ {
    proxy_pass http://pt-guacamole:8080/guacamole/;
    proxy_buffering off;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 3600s;
    proxy_send_timeout 3600s;
}
```
"""
    else:
        buffering_snippet = """
```nginx
# Defective legacy configuration without buffering off
location /guacamole/ {
    proxy_pass http://pt-guacamole:8080/guacamole/;
    proxy_buffers 32 4k;
    proxy_read_timeout 90s;
}
```
"""

    if include_tier4_phase3:
        phase3_section = """
### Phase 3: Enterprise Scaling, Observability & High Availability
- **Scope**: Scale-in/scale-out, connection pooling, monitoring, and DR.
- **Monitoring & Observability**: Deploy Prometheus metrics collectors (cAdvisor, nginx-prometheus-exporter, mysqld_exporter), centralized logging with Docker `json-file` log rotation (max-size 50m, max-file 5).
- **Connection Pooling**: Configure MariaDB `max_connections = 250` and Flask `MySQLConnectionPool` with `pool_size = 15`.
- **High Availability & Sizing**: Sizing pool formulas for 60 concurrent users.

#### Rollback Procedures Across All Implementation Phases
- **Phase 1 Rollback**: Revert `.env` backup (`.env.bak.*`), reload Nginx (`nginx -s reload`).
- **Phase 2 Rollback**: Revert docker-compose configurations, restart legacy containers.
- **Phase 3 Rollback**: Drain dynamic instance pools, restore database from mysqldump.
- **Rollback Trigger Criteria**: Healthcheck failure count > 3 retries, API error rate > 5%, or provisioning timeout rate > 10%.
"""
    else:
        phase3_section = """
### Phase 3: Deferred Scaling
- Scaling topics are left for future revisions.
"""

    template = """# PacketTracerWeb Production Hardening Proposal

## Executive Summary & System Architecture
PacketTracerWeb delivers multi-user browser-based virtualized Cisco Packet Tracer instances through Apache Guacamole, Nginx, and Flask. This proposal presents an exhaustive assessment and technical hardening blueprint covering all 5 core components across all 5 operational domains.

```
       [ Client Browser (HTTPS) ]
                   │
                   ▼ (Port 443 / 5000)
       [ Nginx Edge Gateway (pt-nginx) ]
         ├── TLS 1.2/1.3, Rate Limiting, GeoIP2
         │
         ├──► /guacamole/ (WebSocket / HTTP Tunnel)
         │       │
         │       ▼
         │    [ Apache Guacamole Webapp (pt-guacamole) ] ◄──► [ MariaDB (guacamole-mariadb) ]
         │       │                                             (Named volume mariadb_data)
         │       ▼ (Port 4822)
         │    [ Guacamole Proxy Daemon (guacd) ]
         │       │
         │       ▼ (RFB Port 5901, isolated network)
         │    [ Virtualized PT Containers (ptvnc1..N) ]
         │       ├── TurboVNC + XFCE4 + Cisco Packet Tracer
         │       └── Tini Init, /dev/shm 512MB, 2.5GB RAM
         │
         └──► :5000 (Management Portal)
                 │
                 ▼
              [ Flask / Gunicorn App (pt-management) ]
                 ├── Authenticated REST API & CSRF Protection
                 ├── Isolated Per-User File Storage (/shared/users/{user})
                 └── Docker Socket Proxy (Restricted container-only API)
```

## Verification Resources and Acceptance Criteria Checklist
- [x] Evaluates all five core components: VNC/VirtualGL containers, Guacamole stack, Nginx gateway, Flask management application, and deployment orchestration.
- [x] Covers security, performance, reliability, usability, and maintainability across all components.
- [x] Incorporates verification against existing scripts: `health_check.sh`, `deploy.sh`, `deploy-full.sh`, and `docker-compose.yml`.

---

## 1. Requirement R1: Comprehensive System Assessment

### Component 1: Virtualized Desktop Container (ptvnc)

#### [FINDING-C1-SEC-01] TurboVNC Authentication Disabled with -SecurityTypes None
- **Target Files**: `ptweb-vnc/customizations/start-session`
- **Line Numbers**: Lines 52-58
- **Limitation / Vulnerability Description**: TurboVNC server is launched with `-SecurityTypes None`, leaving RFB port 5901 unauthenticated and vulnerable to session hijacking.
- **Empirical Evidence / Reproduction Command**: `docker exec ptvnc1 ps aux | grep Xvnc` reveals `-SecurityTypes None`.
- **Current Operational Impact**: Any container with network reachability can hijack or monitor desktop sessions.
- **Recommended Direction**: Enforce VNC password authentication via `-PasswordFile` or `-rfbauth` with dynamic credentials.

#### [FINDING-C1-PERF-01] Shared Memory and RAM Undersizing Causing WebEngine Crashes
- **Target Files**: `deploy.sh`, `pt-management/ptmanagement/docker_mgmt/container.py`
- **Line Numbers**: Lines 231-233, Line 333
- **Limitation / Vulnerability Description**: Container `/dev/shm` defaults to 64MB and memory is limited to 512MB in `container.py`, causing Qt6 WebEngine Chromium renderer to crash with code 133 and SIGBUS.
- **Empirical Evidence / Reproduction Command**: Launch Packet Tracer embedded browser with complex simulation; observe `Renderer process crashed - code 133`.
- **Current Operational Impact**: Frequent crashes and UI freezing during student lab exercises.
- **Recommended Direction**: Mandate `/dev/shm >= 512MB` (`shm_size: 512m`) and container RAM >= 2.5GB (`-m 2.5G`).

#### [FINDING-C1-REL-01] Missing Container PID 1 Init System Leaking Zombie Processes
- **Target Files**: `ptweb-vnc/Dockerfile`, `ptweb-vnc/customizations/start`
- **Line Numbers**: Lines 130-135, Lines 20-25
- **Limitation / Vulnerability Description**: Container executes `/start` directly without `tini` init supervisor. AppImage child processes terminate and accumulate as defunct zombies (`[AppRun] <defunct>`).
- **Empirical Evidence / Reproduction Command**: `docker exec ptvnc1 ps -ef | grep defunct` shows accumulated zombie processes.
- **Current Operational Impact**: Host `kernel.pid_max` exhaustion over time, freezing container spawning.
- **Recommended Direction**: Install `tini` and declare `ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/start"]`.

#### [FINDING-C1-USE-01] Autocutsel Clipboard Synchronization Failure
- **Target Files**: `ptweb-vnc/customizations/start-session`
- **Line Numbers**: Lines 70-80
- **Limitation / Vulnerability Description**: Clipboard daemon `autocutsel` is improperly sequenced with TurboVNC, breaking clipboard synchronization between client browser and Cisco Packet Tracer.
- **Empirical Evidence / Reproduction Command**: Copy text from host and attempt paste into Cisco Packet Tracer CLI terminal.
- **Current Operational Impact**: Students unable to paste configurations into virtual routers and switches.
- **Recommended Direction**: Properly daemonize `autocutsel -fork` for both PRIMARY and CLIPBOARD selections.

#### [FINDING-C1-MAINT-01] Shared Volume pt_opt Concurrent Installer Race Condition
- **Target Files**: `ptweb-vnc/customizations/start`, `pt-install.sh`
- **Line Numbers**: Lines 11-18
- **Limitation / Vulnerability Description**: Multiple containers concurrently booting execute `runtime-install.sh` against shared volume `pt_opt` without file locking mutex, corrupting binaries.
- **Empirical Evidence / Reproduction Command**: Boot 5 containers simultaneously; observe partial extraction errors in `/opt/pt`.
- **Current Operational Impact**: Corrupted Packet Tracer binary requiring manual container cleanup.
- **Recommended Direction**: Implement `flock` filesystem mutex on `/opt/pt/.lock` or dedicated installer container.

### Component 2: Apache Guacamole Stack (guacd, webapp, MariaDB)

#### [FINDING-C2-SEC-01] Missing Tomcat RemoteIpValve Causing Proxy IP Ban Lockouts
- **Target Files**: Guacamole Tomcat `server.xml`, `ptweb-vnc/docker-compose.yml`
- **Line Numbers**: Guacamole configuration
- **Limitation / Vulnerability Description**: Tomcat lacks `RemoteIpValve`. `BanningAuthenticationListener` logs Nginx reverse proxy IP (`172.18.0.7`) on failed logins, banning all users globally for 300 seconds.
- **Empirical Evidence / Reproduction Command**: Issue 5 failed login attempts; observe all subsequent logins from different clients blocked.
- **Current Operational Impact**: Platform-wide Denial of Service triggered by a single user's typo.
- **Recommended Direction**: Configure `org.apache.catalina.valves.RemoteIpValve` with `internalProxies` and `remoteIpHeader="x-forwarded-for"`.

#### [FINDING-C2-PERF-01] Enabled Proxy Buffering Inducing High Guacamole Tunnel Latency
- **Target Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Line Numbers**: Lines 45-65
- **Limitation / Vulnerability Description**: Nginx enables `proxy_buffers 32 4k;` and omits `proxy_buffering off;`, buffering Guacamole streaming opcodes and causing severe mouse latency.
- **Empirical Evidence / Reproduction Command**: Drag router icon in Packet Tracer; observe 250ms input lag and jerky rendering.
- **Current Operational Impact**: Poor interactive responsiveness and tunnel disconnections.
- **Recommended Direction**: Set `proxy_buffering off;` and extend `proxy_read_timeout 3600s;`.

#### [FINDING-C2-REL-01] MariaDB Anonymous Volume Causing Permanent Data Loss
- **Target Files**: `ptweb-vnc/docker-compose.yml`
- **Line Numbers**: Lines 15-16
- **Limitation / Vulnerability Description**: MariaDB container lacks a named persistent volume for `/var/lib/mysql`. Executing `docker compose down -v` permanently destroys user and connection databases.
- **Empirical Evidence / Reproduction Command**: Run `docker compose down -v` and observe complete database loss.
- **Current Operational Impact**: Total loss of student accounts, lab mappings, and passwords upon redeployment.
- **Recommended Direction**: Bind named volume `mariadb_data:/var/lib/mysql` with local driver.

#### [FINDING-C2-USE-01] Destructive remove-instance.sh Tearing Down Gateway Stack
- **Target Files**: `remove-instance.sh`
- **Line Numbers**: Lines 148-204
- **Limitation / Vulnerability Description**: Deprovisioning a single instance stops and recreates `guacd`, `guacamole`, and `nginx`, disconnecting all active students platform-wide.
- **Empirical Evidence / Reproduction Command**: Remove container `ptvnc2` while student is active on `ptvnc1`; student 1 is forcibly disconnected.
- **Current Operational Impact**: Scheduled classroom scale-in interrupts concurrent student examinations.
- **Recommended Direction**: Refactor script to stop only the target container and delete database rows without restarting shared services.

#### [FINDING-C2-MAINT-01] Connection Deduplication Failure Due to NULL parent_id
- **Target Files**: `generate-dynamic-connections.sh`
- **Line Numbers**: Lines 60-77
- **Limitation / Vulnerability Description**: In MariaDB, `NULL != NULL`. `INSERT IGNORE` with `parent_id IS NULL` inserts duplicate connection records, causing subqueries to fail with `ERROR 1242 (21000): Subquery returns more than 1 row`.
- **Empirical Evidence / Reproduction Command**: Execute `generate-dynamic-connections.sh` twice consecutively; subquery fails.
- **Current Operational Impact**: Automated connection generator crashes on repeated execution.
- **Recommended Direction**: Implement idempotent upsert with explicit `parent_id` matching.

### Component 3: Nginx Edge Gateway

#### [FINDING-C3-SEC-01] Insecure TLS Ciphers, Missing HSTS, CSP and Security Headers
- **Target Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Line Numbers**: Lines 20-30
- **Limitation / Vulnerability Description**: Permissive cipher string `HIGH:!aNULL:!MD5` allows 3DES. HSTS, CSP, `X-Frame-Options`, and `X-Content-Type-Options` are absent.
- **Empirical Evidence / Reproduction Command**: Inspect response headers via `curl -I https://localhost/`; security headers missing.
- **Current Operational Impact**: Vulnerability to downgrade attacks, MITM, MIME sniffing, and clickjacking.
- **Recommended Direction**: Enforce Mozilla Intermediate ciphers, HSTS (`max-age=63072000`), CSP (`frame-ancestors 'self'`), `X-Frame-Options: SAMEORIGIN`.

#### [FINDING-C3-PERF-01] Absence of TLS Session Caching and OCSP Stapling
- **Target Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Line Numbers**: Lines 15-25
- **Limitation / Vulnerability Description**: Nginx lacks `ssl_session_cache` and `ssl_stapling`, forcing full cryptographic handshakes on every new client connection.
- **Empirical Evidence / Reproduction Command**: Perform multiple TLS handshakes; observe full roundtrip delays.
- **Current Operational Impact**: Increased TLS handshake latency during classroom login spikes.
- **Recommended Direction**: Add `ssl_session_cache shared:SSL:10m;`, `ssl_session_timeout 1d;`, and `ssl_stapling on;`.

#### [FINDING-C3-REL-01] Rate Limiting Colliding with Interactive WebSocket Tunnels
- **Target Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- **Line Numbers**: Lines 60-70
- **Limitation / Vulnerability Description**: General request rate limit `limit_req zone=pt_req_zone burst=200` throttles WebSocket traffic bursts, terminating active sessions with HTTP 503.
- **Empirical Evidence / Reproduction Command**: Perform rapid canvas interactions; tunnel drops with HTTP 503.
- **Current Operational Impact**: Random session drops during intensive network packet simulation.
- **Recommended Direction**: Exclude WebSocket tunnel endpoints from generic HTTP request rate limiting.

#### [FINDING-C3-USE-01] Incorrect ISO Country Codes UK and SL Dropping Legitimate Traffic
- **Target Files**: `ptweb-vnc/pt-nginx/nginx.conf`
- **Line Numbers**: Lines 45-55
- **Limitation / Vulnerability Description**: Nginx map uses non-standard codes `UK` (instead of `GB`) and `SL` (Sierra Leone instead of Sri Lanka `LK`). MaxMind returns `GB`, dropping UK traffic with HTTP 444.
- **Empirical Evidence / Reproduction Command**: Simulate UK client IP `2.125.160.1`; connection drops with HTTP 444.
- **Current Operational Impact**: Legitimate students in UK and Sri Lanka denied platform access.
- **Recommended Direction**: Standardize on ISO 3166-1 alpha-2 codes `GB` and `LK`.

#### [FINDING-C3-MAINT-01] Deprecated MaxMind GeoIP Legacy v1 Module and Hobbyist Mirror
- **Target Files**: `ptweb-vnc/pt-nginx/Dockerfile`, `deploy.sh`
- **Line Numbers**: Line 25, Line 75
- **Limitation / Vulnerability Description**: Uses obsolete `--with-http_geoip_module` and unverified mirror `mailfud.org` for retired `.dat` files.
- **Empirical Evidence / Reproduction Command**: Review build log; downloads from `mailfud.org/geoip-legacy/GeoIP.dat.gz`.
- **Current Operational Impact**: Supply chain risk and unmaintained geolocation database.
- **Recommended Direction**: Migrate to `ngx_http_geoip2_module` with official MaxMind `GeoLite2-Country.mmdb`.

### Component 4: Flask/Gunicorn Management Application

#### [FINDING-C4-SEC-01] Direct Host Docker Socket Mount Running as Root
- **Target Files**: `pt-management/Dockerfile`, `ptweb-vnc/docker-compose.yml`
- **Line Numbers**: Line 12, Lines 74-78
- **Limitation / Vulnerability Description**: Container mounts `/var/run/docker.sock` and executes as root (`UID 0`) without `USER` instruction, granting full host takeover capability.
- **Empirical Evidence / Reproduction Command**: Container has write access to host Docker socket as root.
- **Current Operational Impact**: Total host compromise upon web application exploitation.
- **Recommended Direction**: Interpose `docker-socket-proxy`, enforce `USER ptmgmt` (UID 10001), `cap_drop: [ALL]`, `no-new-privileges: true`.

#### [FINDING-C4-PERF-01] Synchronous Gunicorn Workers Blocking on Bulk Provisioning
- **Target Files**: `pt-management/entrypoint.sh`
- **Line Numbers**: Lines 15-20
- **Limitation / Vulnerability Description**: Gunicorn runs 2 synchronous workers (`--workers 2`). Spawning 30 containers blocks workers for minutes, causing HTTP 504 timeouts on `/health`.
- **Empirical Evidence / Reproduction Command**: Trigger bulk user creation; `/health` probe fails and web portal times out.
- **Current Operational Impact**: Management portal becomes unresponsive during class start.
- **Recommended Direction**: Switch to asynchronous workers (`gevent`) or background task queue (Celery/RQ).

#### [FINDING-C4-REL-01] Lack of MariaDB Connection Pooling and Password Mismatch
- **Target Files**: `pt-management/ptmanagement/db/connection.py`
- **Line Numbers**: Lines 14-25
- **Limitation / Vulnerability Description**: Flask opens/closes raw TCP connections on every query with no pooling. Bulk actions exhaust `max_connections` with `1040: Too many connections`.
- **Empirical Evidence / Reproduction Command**: Run 50 concurrent API requests; MariaDB returns connection limit error.
- **Current Operational Impact**: Database authentication crashes under concurrent student login.
- **Recommended Direction**: Implement `MySQLConnectionPool` with `pool_size = 15` and increase MariaDB `max_connections = 250`.

#### [FINDING-C4-USE-01] Unauthenticated API Bypass and Insecure Default SECRET_KEY
- **Target Files**: `pt-management/app.py`
- **Line Numbers**: Lines 37, 98-136
- **Limitation / Vulnerability Description**: `/api/containers` has unconditional unauthenticated bypass; `/api/users` bypasses auth on spoofable `172.` IP check. Default `SECRET_KEY = 'dev-key-change-in-production'`.
- **Empirical Evidence / Reproduction Command**: Send `POST /api/containers` with no cookies; container is provisioned.
- **Current Operational Impact**: Unauthorized students can spin up arbitrary containers or forge session cookies.
- **Recommended Direction**: Eliminate IP bypasses, require session/token auth, enforce random `SECRET_KEY`, and add `Flask-WTF` CSRF protection.

#### [FINDING-C4-MAINT-01] Single World-Writable /shared Directory Without Tenant Isolation
- **Target Files**: `deploy.sh`, `pt-management/ptmanagement/docker_mgmt/container.py`
- **Line Numbers**: Line 233, Lines 360-370
- **Limitation / Vulnerability Description**: All containers mount shared folder `/shared` with `0777` permissions. Student A can overwrite Student B's `.pkt` files.
- **Empirical Evidence / Reproduction Command**: Write file from container 1; inspect and modify file from container 2.
- **Current Operational Impact**: Cross-tenant data leakage and accidental lab work destruction.
- **Recommended Direction**: Isolate storage per-user (`/shared/users/{username}`) and enforce path traversal checks in Flask API.

### Component 5: Deployment & Orchestration Harness

#### [FINDING-C5-SEC-01] Unscoped Host Cleanup in cleanup-all.sh
- **Target Files**: `Scripts/cleanup-all.sh`
- **Line Numbers**: Lines 47-87
- **Limitation / Vulnerability Description**: Script runs `docker rm $(docker ps -aq)` and `docker volume rm $(docker volume ls -q)`, wiping all unrelated containers on the host.
- **Empirical Evidence / Reproduction Command**: Review script commands; zero project filtering.
- **Current Operational Impact**: Catastrophic data loss for multi-tenant Docker hosts.
- **Recommended Direction**: Filter strictly by project label `label=com.docker.compose.project=ptweb` and require `--purge-data`.

#### [FINDING-C5-PERF-01] 115-Second Hardcoded Sleep Delays in Deployment Sequencing
- **Target Files**: `deploy.sh`, `deploy-full.sh`
- **Line Numbers**: Lines 180-220, Line 88
- **Limitation / Vulnerability Description**: Deployment relies on cumulative 115+ seconds of `sleep` statements rather than dynamic health checks.
- **Empirical Evidence / Reproduction Command**: Measure deployment duration; spends over 2 minutes in static sleep commands.
- **Current Operational Impact**: Unnecessarily prolonged deployment and failure when services take longer than sleep timers.
- **Recommended Direction**: Implement Docker `HEALTHCHECK` and active readiness polling.

#### [FINDING-C5-REL-01] Zero Docker HEALTHCHECK Definitions and Uncoordinated Boot
- **Target Files**: All `Dockerfile`s and `docker-compose.yml`
- **Line Numbers**: Project-wide
- **Limitation / Vulnerability Description**: No containers define `HEALTHCHECK`. Docker Compose `depends_on` lacks `condition: service_healthy`, causing race conditions on startup.
- **Empirical Evidence / Reproduction Command**: Start stack on cold machine; Guacamole crashes before MariaDB finishes initialization.
- **Current Operational Impact**: Boot failures requiring repeated manual restarts.
- **Recommended Direction**: Add `HEALTHCHECK` to MariaDB, guacd, Guacamole, Nginx, and Management, using `condition: service_healthy`.

#### [FINDING-C5-USE-01] Network Divergence Between deploy.sh and deploy-full.sh
- **Target Files**: `deploy.sh`, `deploy-full.sh`, `container.py`
- **Line Numbers**: Network configurations
- **Limitation / Vulnerability Description**: Services split across `ptnet` and `pt-stack` with legacy `--link` flags. Flask connects containers post-creation, causing DNS races (`BULK_INSTANCE_DNS_FIX.md`).
- **Empirical Evidence / Reproduction Command**: Guacamole fails to resolve newly spawned container hostname intermittently.
- **Current Operational Impact**: Intermittent connection failure for freshly provisioned student instances.
- **Recommended Direction**: Unify on bridge network `ptnet` and attach containers at creation time (`network_mode="ptnet"`).

#### [FINDING-C5-MAINT-01] Unpinned Upstream Container Images and Floating Tags
- **Target Files**: `ptweb-vnc/docker-compose.yml`, `deploy.sh`
- **Line Numbers**: Image definitions
- **Limitation / Vulnerability Description**: Uses `mariadb:latest`, `guacamole/guacd:latest`, and unpinned base images, risking breaking changes upon new upstream releases.
- **Empirical Evidence / Reproduction Command**: `docker pull` pulls major updates unexpectedly.
- **Current Operational Impact**: Non-reproducible builds and deployment drift.
- **Recommended Direction**: Pin all images to specific minor versions (e.g. `mariadb:10.11.6`, `guacamole/guacamole:1.5.4`).

---

## 2. Requirement R2: Categorized Improvement Proposals

### Component 1: Virtualized Desktop Container Hardening

#### [PROP-C1-01] Implement Tini Process Supervisor, /dev/shm Sizing and Resource Limits
- **Mapped Findings**: FINDING-C1-REL-01, FINDING-C1-PERF-01
- **Current State & Risk**: Container lacks init system; AppImage sub-processes leak as `[AppRun] <defunct>` zombies. Default 64MB `/dev/shm` causes Qt6 WebEngine crashes.
- **Proposed Solution & Technical Approach**: Install `tini` as PID 1 (`ENTRYPOINT ["/usr/bin/tini", "-g", "--", "/start"]`), set `/dev/shm` to 512MB (`shm_size: 512m` or `--shm-size=512m`), allocate RAM >= 2.5GB (`-m 2.5G`), set ulimits `nofile=65536:65536` and `nproc=4096:4096`. Standardize across constants `RAM=2.5G`, `SHM=512M`, `NOFILE=65536`, `NPROC=4096`, `CPUS=1.5`. Eliminate unmonitored `while true; do sleep 3600; done` loop and evaluate `supervisord`.
- **Impact on Production Stability**: Eliminates defunct zombie leaks, stops SIGBUS WebEngine crashes, stabilizes long-running lab simulations.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Update `ptweb-vnc/Dockerfile` and `docker-compose.yml`; rebuild container image. Revert by redeploying previous image.
- **Affected Components & Files**: `ptweb-vnc/Dockerfile`, `ptweb-vnc/docker-compose.yml`, `deploy.sh`.

#### [PROP-C1-02] TurboVNC Authentication Enforcement and Dynamic Password Management
- **Mapped Findings**: FINDING-C1-SEC-01
- **Current State & Risk**: TurboVNC runs with `-SecurityTypes None`, allowing unauthenticated RFB port access.
- **Proposed Solution & Technical Approach**: Launch TurboVNC with `-PasswordFile` / `-rfbauth` / `vncpasswd`. Generate dynamic per-container passwords stored in MariaDB `guacamole_connection_parameter` (`parameter_name = 'password'`).
- **Impact on Production Stability**: Closes unauthenticated remote desktop access vulnerability.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Update `start-session` and `generate-dynamic-connections.sh`. Revert to previous script version if needed.
- **Affected Components & Files**: `ptweb-vnc/customizations/start-session`, `generate-dynamic-connections.sh`.

#### [PROP-C1-03] Shared Volume pt_opt Mutex Locking During Concurrent Scale-Out
- **Mapped Findings**: FINDING-C1-MAINT-01
- **Current State & Risk**: Concurrent instance booting executes `runtime-install.sh` in parallel into `/opt/pt/`, corrupting binaries.
- **Proposed Solution & Technical Approach**: Add `flock` filesystem mutex on `/opt/pt/.lock` or adopt `docker-compose.installer.yml` pattern before scaling instances.
- **Impact on Production Stability**: Guarantees deterministic, atomic installation on shared storage.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Add `flock` wrapper in `runtime-install.sh`.
- **Affected Components & Files**: `ptweb-vnc/customizations/runtime-install.sh`, `pt-install.sh`.

#### [PROP-C1-04] Autocutsel Clipboard Daemon Sequencing and PulseAudio Audio Streaming
- **Mapped Findings**: FINDING-C1-USE-01
- **Current State & Risk**: Autocutsel clipboard synchronization is erratic; audio is unsupported.
- **Proposed Solution & Technical Approach**: Launch `autocutsel -fork` for PRIMARY and CLIPBOARD after window manager initialization.
- **Impact on Production Stability**: Seamless copy/paste between browser and Cisco Packet Tracer CLI.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Edit `start-session` script.
- **Affected Components & Files**: `ptweb-vnc/customizations/start-session`.

#### [PROP-C1-05] VirtualGL GPU Hardware Acceleration Passthrough with Mesa Fallback
- **Mapped Findings**: FINDING-C1-PERF-01
- **Current State & Risk**: Packet Tracer rendering relies on unoptimized CPU rasterization unless configured.
- **Proposed Solution & Technical Approach**: Configure VirtualGL 3.x (`vglrun`) with `/dev/dri` GPU device passthrough while keeping `--cap-drop=ALL` / `cap_drop: [ALL]` capability dropping, with automatic Mesa OSMesa software rendering fallback.
- **Impact on Production Stability**: High frame rate rendering for complex topology diagrams.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Update container startup configuration.
- **Affected Components & Files**: `ptweb-vnc/Dockerfile`, `ptweb-vnc/customizations/start-session`.

### Component 2: Apache Guacamole Stack Hardening

#### [PROP-C2-01] Configure Tomcat RemoteIpValve to Eliminate Reverse Proxy Ban Lockouts
- **Mapped Findings**: FINDING-C2-SEC-01
- **Current State & Risk**: Tomcat lacks `RemoteIpValve`. Failed logins cause `BanningAuthenticationListener` to ban the Nginx proxy IP, locking out all students.
- **Proposed Solution & Technical Approach**: Add `org.apache.catalina.valves.RemoteIpValve` to Tomcat `server.xml`:
```xml
<Host name="localhost" appBase="webapps">
  <Valve className="org.apache.catalina.valves.RemoteIpValve"
         internalProxies="127\\.\\d+\\.\\d+\\.\\d+|10\\.\\d+\\.\\d+\\.\\d+|172\\.(1[6-9]|2\\d|3[0-1])\\.\\d+\\.\\d+|192\\.168\\.\\d+\\.\\d+"
         remoteIpHeader="x-forwarded-for"
         proxiesHeader="x-forwarded-by"
         protocolHeader="x-forwarded-proto" />
</Host>
```
Nginx configures `proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;` and `proxy_set_header X-Forwarded-Proto $scheme;`.
- **Impact on Production Stability**: Isolates brute-force bans strictly to offending client IP. Nginx proxy IP remains untainted.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Mount custom `server.xml` into Guacamole container; restart container.
- **Affected Components & Files**: Tomcat `server.xml`, `ptweb-vnc/docker-compose.yml`.

#### [PROP-C2-02] Named Persistent Volume mariadb_data and Disaster Recovery
- **Mapped Findings**: FINDING-C2-REL-01
- **Current State & Risk**: Anonymous Docker volume loses all student credentials and connections on `docker compose down -v`.
- **Proposed Solution & Technical Approach**: Declare named volume `mariadb_data:/var/lib/mysql` under `services.mariadb.volumes` and root `volumes: mariadb_data: driver: local`. Implement automated database backup runbook using `mariadb-dump --single-transaction --quick --routines` with daily rotation.
- **Impact on Production Stability**: Guarantees zero data loss across restarts and container upgrades.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Migrate existing data via `docker run --rm -v <anon>:/src:ro -v mariadb_data:/dst alpine cp -a /src/. /dst/`.
- **Affected Components & Files**: `ptweb-vnc/docker-compose.yml`, `deploy.sh`.

#### [PROP-C2-03] Disable Nginx Proxy Buffering and Optimize WebSocket Tunnel
- **Mapped Findings**: FINDING-C2-PERF-01
- **Current State & Risk**: Nginx buffers Guacamole tunnel streams, adding 200ms+ latency and dropping idle sessions at 90s.
- **Proposed Solution & Technical Approach**: Configure `proxy_buffering off;` on `/guacamole/`, configure `$connection_upgrade` map, and extend `proxy_read_timeout 3600s;`.
- **Impact on Production Stability**: Low-latency interactive remote desktop experience.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Update `ptweb.conf` and execute `nginx -s reload`.
- **Affected Components & Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`.

#### [PROP-C2-04] Non-Destructive Deprovisioning in remove-instance.sh
- **Mapped Findings**: FINDING-C2-USE-01
- **Current State & Risk**: Deprovisioning an instance restarts `guacd`, `guacamole`, and `nginx`, disconnecting all users.
- **Proposed Solution & Technical Approach**: Refactor `remove-instance.sh` to check `guacamole_connection_history WHERE end_date IS NULL` for active sessions, remove only targeted `ptvncX` container, and purge SQL record without restarting gateway. Eliminate deprecated `--link` syntax in favor of `ptnet` bridge.
- **Impact on Production Stability**: True zero-downtime scale-in.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Update shell script; preserve previous version as backup.
- **Affected Components & Files**: `remove-instance.sh`.

#### [PROP-C2-05] Idempotent SQL Upsert in generate-dynamic-connections.sh
- **Mapped Findings**: FINDING-C2-MAINT-01
- **Current State & Risk**: `NULL parent_id` unique key quirk leads to duplicate rows and subquery multi-row `ERROR 1242 (21000): Subquery returns more than 1 row`.
- **Proposed Solution & Technical Approach**: Refactor script to use idempotent upsert `ON DUPLICATE KEY UPDATE` or delete existing matching record `DELETE FROM guacamole_connection WHERE connection_name = '$connection_name' AND parent_id IS NULL;` prior to insertion.
- **Impact on Production Stability**: Eliminates script failure and guarantees exactly one record per instance.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Update SQL queries in generator script.
- **Affected Components & Files**: `generate-dynamic-connections.sh`.

### Component 3: Nginx Edge Gateway Hardening

#### [PROP-C3-01] Modern GeoIP2 Migration with ISO Country Code Fixes (GB, LK)
- **Mapped Findings**: FINDING-C3-USE-01, FINDING-C3-MAINT-01
- **Current State & Risk**: Deprecated GeoIP1 module with unofficial `.dat` file from `mailfud.org`; `UK` instead of `GB`, `SL` instead of `LK`. Unanchored and unescaped regex `^(...)|86.50.84.227`.
- **Proposed Solution & Technical Approach**: Migrate to `ngx_http_geoip2_module` using official MaxMind `GeoLite2-Country.mmdb`. Replace `UK 1;` with `GB 1;` and `SL 1;` with `LK 1;`. Replace location-block `if` with top-level `geo $trusted_ip` CIDR blocks:
```nginx
geo $trusted_ip {
    default 0;
    127.0.0.0/8 1;
    10.0.0.0/8 1;
    172.16.0.0/12 1;
    192.168.0.0/16 1;
}
```
Eliminate unanchored regexes and unescaped dots. Provision official `.mmdb` with checksum verification.
- **Impact on Production Stability**: Eliminates unauthorized access blocks for UK and Sri Lankan users; modern supported format.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Compile module in Nginx container; update configuration; reload Nginx.
- **Affected Components & Files**: `ptweb-vnc/pt-nginx/Dockerfile`, `ptweb-vnc/pt-nginx/nginx.conf`, `ptweb.conf`.

#### [PROP-C3-02] Mozilla Intermediate TLS 1.2/1.3 Ciphers, HSTS, and Security Headers
- **Mapped Findings**: FINDING-C3-SEC-01
- **Current State & Risk**: Permissive ciphers, no HSTS, no CSP, missing clickjacking protection.
- **Proposed Solution & Technical Approach**: Enforce Mozilla Intermediate ciphers:
```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384;
ssl_prefer_server_ciphers off;
add_header Strict-Transport-Security "max-age=63072000; includeSubDomains; preload" always;
add_header X-Frame-Options SAMEORIGIN always;
add_header X-Content-Type-Options nosniff always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "frame-ancestors 'self'; connect-src 'self' wss: ws:;" always;
server_tokens off;
```
- **Impact on Production Stability**: Defense against downgrade attacks, SSL stripping, and clickjacking while permitting portal iframe embedding.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Validate with `nginx -t`, then reload.
- **Affected Components & Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`.

#### [PROP-C3-03] TLS Session Caching and OCSP Stapling Optimization
- **Mapped Findings**: FINDING-C3-PERF-01
- **Current State & Risk**: Missing session cache forces full handshake per connection.
- **Proposed Solution & Technical Approach**: Configure `ssl_session_cache shared:SSL:10m;`, `ssl_session_timeout 1d;`, `ssl_session_tickets off;`, `ssl_stapling on;`, `ssl_stapling_verify on; resolver 1.1.1.1 8.8.8.8 valid=300s;`.
- **Impact on Production Stability**: 50% reduction in TLS handshake CPU overhead during class start.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Update Nginx config and reload.
- **Affected Components & Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`.

#### [PROP-C3-04] Exempt WebSocket Tunnels from Generic Request Rate Limiting
- **Mapped Findings**: FINDING-C3-REL-01
- **Current State & Risk**: General HTTP rate limiting drops interactive WebSocket packets.
- **Proposed Solution & Technical Approach**: Separate rate limiting zones: apply rate limiting to HTTP entrypoints while exempting `/guacamole/websocket-tunnel`.
- **Impact on Production Stability**: Prevents HTTP 503 tunnel drops during fast mouse movements.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Adjust `limit_req` directives in `ptweb.conf`.
- **Affected Components & Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`.

#### [PROP-C3-05] Management Port 5000 Perimeter Hardening and Autoindex Removal
- **Mapped Findings**: FINDING-C3-SEC-01
- **Current State & Risk**: Port 5000 lacks security headers; `/downloads/` directory exposes `autoindex on;`.
- **Proposed Solution & Technical Approach**: Apply identical security headers, rate limiting (`limit_req`), and TLS ciphers to port 5000 server block. Enforce `proxy_cookie_path / "/; Secure; HttpOnly; SameSite=Lax"` and disable `autoindex off;` on `/downloads/`.
- **Impact on Production Stability**: Eliminates student file exposure and secures management cookies.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Update port 5000 block in `ptweb.conf`.
- **Affected Components & Files**: `ptweb-vnc/pt-nginx/conf/ptweb.conf`.

### Component 4: Flask Management Service Hardening

#### [PROP-C4-01] Docker Socket Proxy Deployment and Non-Root Execution
- **Mapped Findings**: FINDING-C4-SEC-01
- **Current State & Risk**: Direct `/var/run/docker.sock` mount with root execution allows total host compromise.
- **Proposed Solution & Technical Approach**: Deploy `tecnativa/docker-socket-proxy` restricted to `CONTAINERS=1`, `POST=1`, `INFO=1`, while denying `VOLUMES=0`, `NETWORKS=0`, `SWARM=0`, `SYSTEM=0`, `EXEC=0`, `AUTH=0`, `SECRETS=0`. Run Flask container as `USER ptmgmt` (UID 10001, GID 10001), with `cap_drop: [ALL]`, `--cap-drop=ALL`, `security_opt: [no-new-privileges:true]`, and `read_only: true` with `tmpfs: [/tmp, /app/logs]`. Remove host project root mount `-v "$ROOT_DIR:/project"`.
- **Impact on Production Stability**: Neutralizes container escape attacks and restricts API capabilities strictly to container lifecycle.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Update `docker-compose.yml`, rebuild `pt-management/Dockerfile`.
- **Affected Components & Files**: `pt-management/Dockerfile`, `ptweb-vnc/docker-compose.yml`.

#### [PROP-C4-02] Remove Authentication Bypasses and Enforce CSRF Protection
- **Mapped Findings**: FINDING-C4-USE-01
- **Current State & Risk**: Unauthenticated `/api/containers` bypass and spoofable `172.` / `10.` IP bypass on `/api/users`. Default `SECRET_KEY = 'dev-key-change-in-production'`.
- **Proposed Solution & Technical Approach**: Remove unconditional `/api/containers` bypass and `client_ip.startswith('172.')` / `10.` checks. Enforce session authentication or `Authorization: Bearer <API_TOKEN>` for automation. Integrate `Flask-WTF` `CSRFProtect(app)` across forms (`<input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>`) and AJAX requests (`X-CSRFToken`). Generate dynamic cryptographically random `SECRET_KEY` via `secrets.token_hex(32)`.
- **Impact on Production Stability**: Prevents unauthorized container spawning, spoofed user creation, and session forgery.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Update `app.py` and templates; revert via git commit.
- **Affected Components & Files**: `pt-management/app.py`, `pt-management/config.py`.

#### [PROP-C4-03] Asynchronous Worker Model for Long-Running Provisioning
- **Mapped Findings**: FINDING-C4-PERF-01
- **Current State & Risk**: Synchronous Gunicorn workers block during bulk container provisioning.
- **Proposed Solution & Technical Approach**: Switch Gunicorn to asynchronous worker model (`gevent`) or implement background job queue (Celery/RQ) for provisioning tasks.
- **Impact on Production Stability**: Preserves responsiveness of `/health` probes and user requests during bulk operations.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Update `entrypoint.sh` worker class.
- **Affected Components & Files**: `pt-management/entrypoint.sh`.

#### [PROP-C4-04] MariaDB Connection Pooling in Flask Application
- **Mapped Findings**: FINDING-C4-REL-01
- **Current State & Risk**: Unpooled database connections exhaust server connection limit under load.
- **Proposed Solution & Technical Approach**: Implement `MySQLConnectionPool` with `pool_size = 15` in `ptmanagement/db/connection.py`. Fix variable name divergence (`DB_PASSWORD` vs `DB_PASS`). Configure MariaDB server `max_connections = 250`.
- **Impact on Production Stability**: Stable database connectivity during classroom concurrency spikes.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Update database connector module.
- **Affected Components & Files**: `pt-management/ptmanagement/db/connection.py`.

#### [PROP-C4-05] Tenant-Isolated Per-User Directory Architecture
- **Mapped Findings**: FINDING-C4-MAINT-01
- **Current State & Risk**: Global world-writable `/shared` allows cross-student file snooping and deletion.
- **Proposed Solution & Technical Approach**: Mount user-isolated subdirectories `/shared/users/{{username}}:/home/ptuser/shared` into each container. Implement path traversal validation in Flask file manager API (`Path.relative_to`).
- **Impact on Production Stability**: Complete privacy and integrity for student lab files.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Create user subdirectories and update container creation mounts.
- **Affected Components & Files**: `pt-management/ptmanagement/docker_mgmt/container.py`, `routes.py`.

### Component 5: Deployment & Orchestration Hardening

#### [PROP-C5-01] Docker HEALTHCHECK Implementation and Zero-Sleep Startup
- **Mapped Findings**: FINDING-C5-REL-01, FINDING-C5-PERF-01
- **Current State & Risk**: Absence of health probes; deployment delayed by 115 seconds of arbitrary sleep calls.
- **Proposed Solution & Technical Approach**: Add `HEALTHCHECK` instructions:
  - MariaDB: `mariadb-admin ping -h localhost -u root -p$$MARIADB_ROOT_PASSWORD` (interval 5s, timeout 3s, retries 5, start_period 10s)
  - Guacd: `nc -z localhost 4822` (interval 5s, timeout 3s, retries 5)
  - Guacamole: `curl -f -s http://localhost:8080/guacamole/` (interval 10s, timeout 5s, retries 6, start_period 30s)
  - Management: `curl -f -s http://localhost:5000/health`
  - VNC Container: `nc -z localhost 5901`
  Configure `depends_on: mariadb: condition: service_healthy` in `docker-compose.yml`. Replace hardcoded sleep commands in deployment scripts with active healthcheck polling loops.
- **Impact on Production Stability**: 80% reduction in deployment time; eliminates startup race conditions.
- **Implementation Complexity**: Medium.
- **Migration Steps / Rollback**: Update `docker-compose.yml` and `deploy.sh`.
- **Affected Components & Files**: `docker-compose.yml`, `deploy.sh`, `deploy-full.sh`.

#### [PROP-C5-02] Network Topology Standardization and Race Elimination
- **Mapped Findings**: FINDING-C5-USE-01
- **Current State & Risk**: Network split between `ptnet` and `pt-stack`; asynchronous connect triggers DNS races (`BULK_INSTANCE_DNS_FIX.md`).
- **Proposed Solution & Technical Approach**: Standardize on user-defined bridge network `ptnet` (segmented into `frontend-net`, `backend-net`, `vnc-net`). Directly attach new containers at creation time (`network_mode="ptnet"`), eliminating post-creation connect calls and legacy `--link` syntax.
- **Impact on Production Stability**: Instant DNS resolution and zero container reachability failures.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Unify network definitions across compose and management code.
- **Affected Components & Files**: `deploy.sh`, `deploy-full.sh`, `pt-management/ptmanagement/docker_mgmt/container.py`.

#### [PROP-C5-03] Container Capability Dropping and Security Profiles
- **Mapped Findings**: FINDING-C5-SEC-01
- **Current State & Risk**: Containers run with default elevated Linux capabilities.
- **Proposed Solution & Technical Approach**: Enforce `cap_drop: [ALL]` and `--cap-drop=ALL` across all services. Grant `--security-opt=no-new-privileges:true`. Explicitly pass only necessary devices (`/dev/dri` for VirtualGL GPU access).
- **Impact on Production Stability**: Hardened container isolation against kernel exploit chains.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Add security options to `docker-compose.yml`.
- **Affected Components & Files**: `ptweb-vnc/docker-compose.yml`.

#### [PROP-C5-04] Scoped Maintenance Scripts and Volume Protection
- **Mapped Findings**: FINDING-C5-SEC-01
- **Current State & Risk**: `cleanup-all.sh` wipes entire Docker host.
- **Proposed Solution & Technical Approach**: Scope cleanup commands strictly to project label `com.docker.compose.project=ptweb`. Protect `mariadb_data` volume from automated purge; mandate explicit `--purge-data` confirmation flag.
- **Impact on Production Stability**: Prevents catastrophic loss of external host containers or database volumes.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Replace `cleanup-all.sh` with project-scoped commands.
- **Affected Components & Files**: `Scripts/cleanup-all.sh`.

#### [PROP-C5-05] Upstream Image Pinning and Automated Backup Lifecycle
- **Mapped Findings**: FINDING-C5-MAINT-01
- **Current State & Risk**: Unpinned image tags cause deployment drift; no automated backup rotation.
- **Proposed Solution & Technical Approach**: Pin container tags: `mariadb:10.11.6`, `guacamole/guacamole:1.5.4`, `guacamole/guacd:1.5.4`. Implement automated MariaDB backup script with cron rotation (7 daily, 4 weekly) capturing standard schema and custom `user_container_mapping` table.
- **Impact on Production Stability**: Predictable, reproducible deployments and guaranteed disaster recovery.
- **Implementation Complexity**: Low.
- **Migration Steps / Rollback**: Update compose image tags; verify database backups.
- **Affected Components & Files**: `docker-compose.yml`, `Scripts/backup-mariadb.sh`.

---

## 3. Requirement R2: Cross-Feature Synergy & Architectural Interlocks

__BUFFERING_SNIPPET__

### Interlock Matrix & Cross-Component Alignments
1. **Nginx Buffering vs Guacamole WebSockets**: Disabling proxy buffering and setting `$connection_upgrade` ensures real-time mouse rendering and prevents 90s idle timeouts (`proxy_read_timeout 3600s`).
2. **GeoIP2 Rules vs WebSocket Tunnels**: ISO code corrections (`GB`, `LK`) prevent false geographic drops; WebSockets are exempted from generic HTTP burst rate limiting.
3. **Tomcat RemoteIpValve vs Ban Lockouts**: Passing client IP via `X-Forwarded-For` and `RemoteIpValve` isolates failed login bans to attackers without affecting the Nginx proxy IP.
4. **Frame Options vs Portal Iframe**: Security headers use `X-Frame-Options: SAMEORIGIN` and CSP `frame-ancestors 'self'` to allow legitimate web portal embedding while blocking third-party clickjacking.
5. **TLS Ciphers vs Modern WebSockets**: Mozilla Intermediate ciphers and ALPN ensure strong encryption with zero WebSocket handshake friction.
6. **Flask Provisioning vs Guacamole Reachability**: Attaching containers to `ptnet` at creation time (`network_mode`) eliminates post-creation connect races (`BULK_INSTANCE_DNS_FIX.md`).
7. **Socket Proxy Scope vs Flask Non-Root Capabilities**: Scoping socket proxy to `CONTAINERS=1`, `POST=1` allows container lifecycle management while blocking volume and system tampering under non-root `USER ptmgmt`.
8. **Shared Volume Mutex vs Scale-Out**: File mutex `flock` on `/opt/pt/.lock` prevents concurrent `.deb` extraction corruption.
9. **Per-User File Isolation vs File Manager API**: Partitioning `/shared/users/{user}` with `Path.relative_to` validation prevents directory traversal and peer data leakage.
10. **Gunicorn Async Workers vs Docker API**: Switching to `gevent` prevents long provisioning operations from blocking Flask `/health` probes.
11. **MariaDB Connection Pooling vs Concurrency**: Flask connection pool (`pool_size = 15`) and MariaDB `max_connections = 250` prevent exhaustion under 60-student load.
12. **MariaDB Volume Persistence vs Deduplication**: Named volume `mariadb_data` prevents data loss while idempotent SQL eliminates `ERROR 1242` duplicate connection crashes.
13. **TurboVNC Password Generation vs Guacamole Parameters**: Dynamically generated passwords stored in MariaDB eliminate `-SecurityTypes None`.
14. **Persistent SECRET_KEY vs Session Continuity**: Cryptographic `SECRET_KEY` persistence prevents session invalidation on container restart.
15. **MariaDB Automated Backup vs Mapping Synchronization**: Backup script captures standard Guacamole tables and `user_container_mapping`.
16. **Tini Supervisor vs Zombie Reaping**: PID 1 init reaps defunct `[AppRun] <defunct>` sub-processes on `SIGCHLD`.
17. **dev/shm & Memory vs VirtualGL Qt6 Rendering**: 512MB shared memory and 2.5GB RAM eliminate Chromium WebEngine crash 133 and SIGBUS faults.
18. **Docker Healthchecks vs Zero-Sleep Deployment**: Replacing 115s sleep delays with `condition: service_healthy` accelerates bootstrapping safely.
19. **Non-Destructive Scale-In vs Session Persistence**: Selective removal of target `ptvncX` preserves active student sessions on remaining instances.
20. **Capability Dropping vs GPU Passthrough**: Container security profiles drop root privileges while preserving `/dev/dri` and `video` group permissions.

---

## 4. Production Hardening Roadmap & Operational Runbooks

### 4.1 Phased Rollout Roadmap

#### Phase 1: Zero-Downtime Hotfixes & Security Patches
- **Scope**: Immediate security hardening without container rebuilds or scheduled downtime.
- **Actions**:
  - Eliminate default credentials (`IlovePT`, `Cisco123`) and inject strong environment passwords.
  - Mount Tomcat `RemoteIpValve` in `server.xml` to prevent proxy IP ban lockouts.
  - Remove unconditional `/api/containers` and `172.` IP authentication bypasses in Flask.
  - Fix destructive `cleanup-all.sh` to scope operations to `label=com.docker.compose.project=ptweb`.
  - Apply Nginx security headers (`X-Frame-Options: SAMEORIGIN`, HSTS) and reload Nginx (`nginx -s reload`).

#### Phase 2: Architectural Decoupling & Structural Hardening
- **Scope**: Container rebuilds, persistent storage migration, and process supervision.
- **Actions**:
  - Deploy `tecnativa/docker-socket-proxy` and enforce non-root `USER ptmgmt` (UID 10001).
  - Migrate anonymous database volume to named volume `mariadb_data`.
  - Install `tini` as PID 1 in `ptweb-vnc` and configure `shm_size: 512m` and RAM >= 2.5GB.
  - Transition from global `/shared` to per-user isolated directories `/shared/users/{user}`.
  - Migrate Nginx to `ngx_http_geoip2_module` with official `.mmdb` databases and ISO fixes (`GB`, `LK`).

__PHASE3_SECTION__

### 4.2 Migration, Verification & Disaster Recovery Runbooks

#### Pre-Migration Verification Checklist
- Host Kernel Settings: `kernel.pid_max >= 65536`, `fs.file-max >= 2097152`.
- Docker Engine & Compose: Docker Engine >= 24.0, Compose v2 >= 2.20.
- Port Availability: 80, 443, 5000, 3306, 4822 available.
- Hardware Capacity: Host RAM calculation: min 16GB for 8 users, min 64GB for 32 users.
- Dry-Run Syntax Validation: `docker compose config` and `nginx -t`.

#### MariaDB Backup and Restore Disaster Recovery Runbook
- Non-blocking backup command:
  ```bash
  mariadb-dump -h localhost -u root -p"$DB_ROOT_PASS" --single-transaction --quick --routines --triggers guacamole_db | gzip > /backups/guacamole_$(date +%Y%m%d_%H%M%S).sql.gz
  ```
- Recovery Targets: RPO <= 15 minutes, RTO <= 30 minutes. Retention: 7 daily, 4 weekly backups.
- Safe Anonymous-to-Named Volume Migration Procedure:
  ```bash
  docker run --rm -v ptweb_anon_vol:/src:ro -v mariadb_data:/dst alpine cp -a /src/. /dst/
  ```

### 4.3 Software Compatibility Verification
- **Cisco Packet Tracer 8.x**: Compatible with versions 8.1.x and 8.2.x (`CiscoPacketTracer.deb`). Verified Linux runtime dependencies: Qt6 libraries (`libqt6core6`, `libqt6gui6`, `libqt6widgets6`), `libgl1-mesa-glx`, `libgl1-mesa-dri`. Supports non-interactive extraction and `.pkt` / `.pka` network simulation files.
- **TurboVNC & VirtualGL**: TurboVNC 3.x and VirtualGL 3.x (`vglrun`). Redundant `Xvfb` on `:1` eliminated in `start-session` to prevent display server collisions. `autocutsel` clipboard synchronization verified.
- **Apache Guacamole Stack**: Pinned image tags `guacamole/guacamole:1.5.4` and `guacamole/guacd:1.5.4`. Schema compatibility verified for standard tables and custom `user_container_mapping`. Web client supports HTML5 Canvas and WebSocket RFC 6455 with HTTP tunnel fallback.

### 4.4 Operational Incident Runbooks

#### Incident Response Runbook: Guacamole IP Ban Lockout
1. **Diagnosis**: Check Guacamole Tomcat logs for `BanningAuthenticationListener` banning proxy IP.
2. **Emergency Remediation**: Clear failed login records in MariaDB:
   ```sql
   DELETE FROM guacamole_user_history WHERE end_date IS NULL;
   ```
3. **Permanent Verification**: Confirm `RemoteIpValve` is loaded in `server.xml` and Nginx sends `X-Forwarded-For`.

#### Incident Response Runbook: Zombie Process Storm
1. **Detection**: Check process table for accumulating `[AppRun] <defunct>` entries.
2. **Emergency Triage**: Signal container with `docker kill -s SIGTERM ptvncX` or restart container.
3. **Permanent Remediation**: Verify `tini` is configured as PID 1 entrypoint with `-g` flag.

#### Classroom Peak Scaling Runbook (60 Concurrent Students)
1. **Capacity Planning Formulas**:
   - Host RAM Required: $(N \times 2.5\text{GB}) + 4\text{GB} = (60 \times 2.5) + 4 = 154\text{GB}$ RAM.
   - Host CPU Cores Required: $(N \times 0.5) + 2 = (60 \times 0.5) + 2 = 32$ cores.
2. **Pre-Warming Strategy**: Pre-provision 20 standby containers 15 minutes before lab start.
3. **Deprovisioning Runbook**: Graceful shutdown of idle containers, archival of student files, resource reclamation.

#### File Isolation and Multi-Tenant Security Acceptance Scenario
- **Confidentiality**: Student A cannot access Student B's saved `.pkt` files.
- **Path Traversal Defense**: Flask API rejects `../` and absolute paths in `/api/files/download`.
- **Disk Quotas**: 100MB disk quota per user directory prevents host storage exhaustion.
"""

    return template.replace("__BUFFERING_SNIPPET__", buffering_snippet).replace("__PHASE3_SECTION__", phase3_section)
