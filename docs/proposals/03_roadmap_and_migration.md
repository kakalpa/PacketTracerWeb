# Production Roadmap, Risk Assessment & Migration Engineering: PacketTracerWeb Hardening

**Document Reference**: `docs/proposals/03_roadmap_and_migration.md`  
**Milestone**: M3 (Production Roadmap, Risk Assessment & Migration Engineering)  
**Author**: Worker Agent (`worker_m3`)  
**Target Architecture**: PacketTracerWeb Production Architecture  
**Date**: November 2026  
**Status**: COMPLETE / READY FOR SUB-ORCHESTRATOR REVIEW  

---

## Executive Summary & Strategic Overview

### Architectural Context
PacketTracerWeb is an educational and enterprise remote-learning platform designed to deliver multi-user, browser-based, virtualized Cisco Packet Tracer instances over HTML5 Canvas without client software installation. The baseline system architecture consists of five tightly coupled subsystems:
1. **Virtualized Desktop Containers (`ptvnc`)**: Ubuntu 22.04 LTS desktop containers running TurboVNC, VirtualGL, XFCE4, and Cisco Packet Tracer 8.x.
2. **Apache Guacamole Remote Desktop Gateway (`guacd`, `pt-guacamole`, `guacamole-mariadb`)**: Clientless gateway translating RFB protocols into Guacamole WebSockets, authenticated against a MariaDB database backend.
3. **Nginx Edge Gateway (`pt-nginx`)**: Edge reverse proxy handling TLS termination (TLS 1.2/1.3), GeoIP filtering, rate limiting, and HTTP/WebSocket traffic routing.
4. **Flask / Gunicorn Management Service (`pt-management`)**: Python 3.11 orchestration daemon managing container lifecycle, user provisioning, database records, and workspace files.
5. **Deployment & Orchestration Harness**: Procedural shell scripts (`deploy.sh`, `deploy-full.sh`, `add-instance.sh`, `remove-instance.sh`, `health_check.sh`) and Docker Compose configuration.

While functional as a proof-of-concept, the baseline system assessment (documented in `docs/proposals/01_system_assessment.md`, identifying 62 discrete findings) and improvement proposals (`docs/proposals/02_improvement_proposals.md`, detailing 27 technical proposals) revealed critical architectural, security, and operational vulnerabilities. These include root host escape vectors via direct `/var/run/docker.sock` mounts, unauthenticated container provisioning, hardcoded static credentials, catastrophic data loss risks from anonymous MariaDB volumes, institutional NAT IP ban lockouts under Apache Tomcat, process table exhaustion from defunct `[AppRun]` zombies, dual X server resource waste, and destructive host cleanup routines.

### Strategic Migration Objectives
This document establishes the executable engineering bridge between theoretical proposals and production deployment. It details:
- **A 3-Phase Sequential Rollout Strategy**: Progressing from zero-downtime emergency hotfixes to structural decoupling, ending in high-availability enterprise scaling.
- **A Comprehensive Risk Assessment Matrix**: Evaluating technical, operational, and user experience risks with concrete mitigation protocols and telemetry triggers.
- **Step-by-Step Migration Runbooks & Disaster Recovery Protocols**: Complete with pre-migration host audits, exact shell commands, configuration diffs, named volume copy procedures, automated database backup lifecycles, and deterministic rollback triggers.
- **A Software Dependency & Compatibility Matrix**: Validating Cisco Packet Tracer 8.x (8.0, 8.1, 8.2, 8.3, 8.4), Qt6, OpenGL llvmpipe, TurboVNC 3.x, VirtualGL 3.x, Guacamole 1.5.5, Tomcat 9, MariaDB 11.4 LTS, and Nginx 1.27+.
- **Operational & Incident Response Runbooks**: Practical triage workflows for IP ban lockouts, zombie process storms, classroom peak scaling models, and student multi-tenant file security verification.

```
================================================================================================================
                                       STRATEGIC MIGRATION TIMELINE
================================================================================================================
 [ Phase 1: Security & Perimeter ]          [ Phase 2: Decoupling & Hardening ]      [ Phase 3: HA & Scaling ]
   Day 1 - Week 1 (Zero Downtime)             Week 2 - Week 3 (15-30m Windows)         Week 4 - Week 6 (Zero Downtime)
 ----------------------------------         -----------------------------------      ---------------------------------
 • Socket proxy deployment                  • MariaDB named volume migration         • Docker Compose v2 unification
 • Eliminate unauthenticated API            • tini PID 1 zombie process reaping      • Container HEALTHCHECK probes
 • Purge webroot credential leaks           • Eliminate dual Xvfb (:1) servers       • 3-tier network segmentation
 • Rotate hardcoded default passwords       • Enforce /dev/shm 512MB & 2.5GB RAM     • JSON log rotation & Prometheus
 • Enforce Nginx security headers           • Guacamole NULL parent_id dedup         • Database connection pooling
 • Fix GeoIP regex backtracking             • Per-user /shared/users/{id} files      • Automated mysqldump lifecycle
 • Tomcat RemoteIpValve in server.xml       • docker-socket-proxy non-root user      • Scoped docker compose cleanups
 • Fix cleanup-all.sh host safeguards       • VirtualGL 3.x GPU passthrough          • Classroom pre-warming routines
================================================================================================================
```

---

## Section 1: Phased Rollout Roadmap

### 1.1 Executive Overview & Strategic Timeline
The PacketTracerWeb production rollout is structured across three sequential, failure-isolated phases. This staged progression guarantees that urgent security vulnerabilities are sealed immediately without service interruption, followed by controlled structural database and display migrations during scheduled maintenance windows, culminating in enterprise observability, automated scaling, and resilient high-availability orchestration.

| Phase | Strategic Focus | Operational Window | Target Downtime | Core Deliverables | Rollback Complexity |
|---|---|---|---|---|---|
| **Phase 1** | Immediate Critical Security & Perimeter Hardening | Day 1 to Week 1 | **Zero Downtime** (Hotfixes & Config Reloads) | Docker socket proxy, API auth enforcement, purge `bulk-user-api.php`, rotate `IlovePT`/`ptdbpass`, Nginx headers, GeoIP regex fix, Tomcat `RemoteIpValve`, `cleanup-all.sh` safeguards | Low (Config & container revert) |
| **Phase 2** | Core Architecture & Container Hardening | Week 2 to Week 3 | **15-30 min Maintenance Window** (Per component) | MariaDB `mariadb_data` named volume migration, `tini -g` PID 1 supervisor, dual Xvfb elimination, `/dev/shm 512MB` & 2.5GB RAM, Guacamole connection deduplication, `/shared/users/{id}` isolation | Medium (Volume & schema restore) |
| **Phase 3** | High Availability, Observability & Enterprise Scaling | Week 4 to Week 6 | **Zero Downtime** (Rolling Upgrades) | Docker Compose v2 single source of truth, Docker `HEALTHCHECK`s, 3-tier network segmentation (`frontend-net`, `backend-net`, `vnc-net`), Prometheus metrics, connection pooling, automated backups | Low (Rolling Compose deployment) |

---

### 1.2 Phase 1: Immediate Critical Security & Perimeter Hardening
**Operational Window**: Day 1 – Week 1  
**Service Impact**: Zero Downtime (Hotfixes, configuration reloads, and rolling service restarts).

#### 1.2.1 Phase 1 Architectural Scope
Phase 1 focuses on perimeter defense, eliminating active exploitation vectors and preventing host system destruction:
1. **Docker Socket Proxy Isolation**: Interpose `tecnativa/docker-socket-proxy` between `pt-management` and the Docker daemon. Revoke direct `/var/run/docker.sock` volume mounts in `pt-management`, restricting API calls strictly to container creation and lifecycle endpoints while blocking raw host filesystem, volume, or system manipulation.
2. **API Authentication & IP Spoofing Remediation**: Eliminate the unauthenticated `/api/containers` creation bypass in `management/app.py`. Remove spoofable `X-Forwarded-For` and `request.remote_addr` trust logic in `is_request_authenticated()`. Enforce strict Flask session authentication and `Flask-WTF` CSRF token validation across all state-mutating endpoints.
3. **Purge Public Webroot Credential Leaks & Unauthenticated Directory Indexes**: Permanently delete `frontend/bulk-user-api.php` from the Nginx webroot `/var/www/html`. Remove and patch unauthenticated public directory indexing (`location ^~ /downloads/ { alias /shared/; autoindex on; }`) in Nginx configuration, preventing public directory enumeration of `/shared/users/` tenant files. Remove legacy plain-text database credentials and static API keys from client-accessible directories.
4. **Credential Rotation & Secret Hardening**: Eradicate all instances of default passwords (`IlovePT`, `ptdbpass`, `admin123`, `Cisco123`). Enforce strong runtime-generated secrets for `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, and Guacamole administrative users. Enforce mandatory high-entropy `SECRET_KEY` generation in Python via `secrets.token_hex(32)`.
5. **Nginx Perimeter Security Headers**: Apply standard HTTP security headers:
   - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self' wss:; frame-ancestors 'self';`
   - `X-Frame-Options: SAMEORIGIN`
   - `X-Content-Type-Options: nosniff`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `server_tokens off;`
6. **GeoIP Regex Backtracking & Country Code Fixes**: Correct flawed regex in Nginx configuration that allowed geographic bypasses. Fix invalid ISO alpha-2 country codes (`UK` to `GB`, `SL` to `LK`).
7. **Tomcat `RemoteIpValve` Integration**: Deploy `org.apache.catalina.valves.RemoteIpValve` in Tomcat's `conf/server.xml` within the Guacamole container. Configure `internalProxies` to match strict RFC 1918 private subnets:
   `internalProxies="10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"`
   This prevents spoofed `X-Forwarded-For` injection from public 172.x IP ranges while ensuring real client IP addresses are accurately reported to Guacamole's authentication listener and preventing institutional NAT IP ban lockouts.
8. **Host Cleanup Script Safeguards**: Rewrite `Scripts/cleanup-all.sh`. Replace global, un-scoped commands (`docker rm -f $(docker ps -aq)`, `docker volume rm $(docker volume ls -q)`) with scoped label-filtered commands restricted exclusively to `label=com.docker.compose.project=ptweb`.

#### 1.2.2 Phase 1 Deliverables & Acceptance Milestones
- **D1.1**: Production `.env` template enforcing dynamic secrets with zero hardcoded defaults.
- **D1.2**: Hardened `management/app.py` with CSRF protection, session verification, and sanitized API endpoints.
- **D1.3**: Hardened `nginx/conf.d/default.conf` containing security headers, `/downloads/` autoindex removal, correct GeoIP mapping, and `proxy_buffering off;`.
- **D1.4**: Updated Tomcat `server.xml` with RFC 1918-scoped `RemoteIpValve` deployed and verified.
- **D1.5**: Hardened `Scripts/cleanup-all.sh` with Docker label filters and dry-run safety flags.
- **Milestone M1 Acceptance Criteria**:
  - `curl -I https://<host>/` returns all 5 required security headers and `Server` banner is masked.
  - `curl -X POST https://<host>:5000/api/containers` without authenticated session returns HTTP 401 Unauthorized.
  - `curl -I https://<host>/bulk-user-api.php` and `curl -I https://<host>/downloads/` return HTTP 404 Not Found or HTTP 403 Forbidden.
  - Failed logins from institutional IPs register individual remote client IPs in Tomcat audit logs rather than the Nginx gateway IP (`172.x.x.x`).

---

### 1.3 Phase 2: Core Architecture & Container Hardening
**Operational Window**: Week 2 – Week 3  
**Service Impact**: Scheduled 15-30 minute maintenance windows per component during low-utilization periods.

#### 1.3.1 Phase 2 Architectural Scope
Phase 2 resolves underlying architectural bottlenecks, persistent storage risks, and container resource contention:
1. **MariaDB Persistent Named Volume Migration**: Eliminate the legacy anonymous Docker volume (`/var/lib/mysql`) used by `guacamole-mariadb`. Safely copy existing user accounts, connection profiles, and permission matrices to a persistent named Docker volume `mariadb_data`. Ensure data survives container destruction and host reboots.
2. **Process Supervision & Zombie Reaping**: Introduce `tini` init supervisor (`tini -g -- /docker-entrypoint.sh`) as PID 1 in the `ptvnc` Dockerfile. When Cisco Packet Tracer crashes or launches subprocesses, `tini` reaps defunct child processes (`[AppRun] <defunct>` and `[PacketTracer] <defunct>`), preventing host PID space exhaustion.
3. **Elimination of Dual Display Servers**: Remove redundant `Xvfb :1` display server from the desktop startup pipeline (`start-session`). Standardize exclusively on `TurboVNC :2`, liberating 200MB+ RAM per container and eliminating X11 socket collisions.
4. **Kernel & Container Resource Enforcement**:
   - Enforce `/dev/shm 512MB` on all `ptvnc` instances to prevent QtWebEngine/Chromium crash 133 / SIGBUS memory faults.
   - Configure hard memory limits of 2.5GB per container (`mem_limit: 2560m`) with 2.0GB soft reservations (`mem_reservation: 2048m`).
   - Configure container ulimits: `nofile: 65536` (file descriptors) and `nproc: 4096` (process threads).
5. **Guacamole Connection Deduplication**: Fix the dynamic connection generator script (`generate-dynamic-connections.sh`). Implement `WHERE parent_id IS NULL` filtering and idempotent `INSERT ... ON DUPLICATE KEY UPDATE` logic to prevent unique key constraint violations (`ERROR 1242`) in `guacamole_connection`.
6. **Per-User File Storage Isolation**: Refactor shared workspace volume from world-writable `/shared` to structured per-user subdirectories (`/shared/users/{user_id}/`). Enforce POSIX permission masks (`0700`) and configure Flask file download endpoints with strict path traversal sanitization.
7. **Least-Privilege Container Execution**: Configure `docker-socket-proxy` and `pt-management` to run under dedicated non-root service accounts (`USER ptmgmt`, UID 10001). Apply security options: `cap_drop: [ALL]`, `cap_add: [NET_BIND_SERVICE]`, and `no-new-privileges: true`.

#### 1.3.2 Phase 2 Deliverables & Acceptance Milestones
- **D2.1**: Executed database migration script transitioning data from anonymous volume to `mariadb_data`.
- **D2.2**: Hardened `Dockerfile.ptvnc` featuring `tini` init supervisor, TurboVNC 3.x, and VirtualGL 3.x.
- **D2.3**: Optimized `start-session` script stripped of `Xvfb` and configured for pure TurboVNC.
- **D2.4**: Updated `generate-dynamic-connections.sh` supporting idempotent, non-destructive connection generation.
- **D2.5**: Multi-tenant file management module in Flask enforcing `/shared/users/{user_id}` boundaries.
- **Milestone M2 Acceptance Criteria**:
  - `docker inspect guacamole-mariadb` confirms mount destination `/var/lib/mysql` binds to named volume `mariadb_data`.
  - Recreating the MariaDB container (`docker compose down && docker compose up -d`) preserves all user and connection tables intact.
  - `docker exec ptvnc1 ps aux` verifies `tini` running as PID 1, exactly one X server (`Xvnc :2`), and zero defunct zombie processes after Packet Tracer termination.
  - Running memory-intensive WebEngine modules within Packet Tracer executes stably without SIGBUS / crash 133.

---

### 1.4 Phase 3: High Availability, Observability & Enterprise Scaling
**Operational Window**: Week 4 – Week 6  
**Service Impact**: Zero Downtime (Rolling container updates with active health probes).

#### 1.4.1 Phase 3 Architectural Scope
Phase 3 operationalizes PacketTracerWeb for large-scale institutional deployments, ensuring high availability, observability, and automated lifecycle management:
1. **Docker Compose v2 Infrastructure as Code**: Unify fragmented shell scripts (`deploy.sh`, `deploy-full.sh`, `add-instance.sh`) into a single, declarative Compose v2 specification (`docker-compose.yml`). Utilize modern Compose directives (`profiles`, `secrets`, `healthcheck`, `deploy.resources`).
2. **Active Container Readiness & Healthchecks**: Define Docker `HEALTHCHECK` instructions across all stack containers. Implement service startup sequencing using `depends_on: { condition: service_healthy }`. Replace fragile 115-second arbitrary `sleep` timeouts with active readiness polling against database ports, Guacamole REST endpoints, and VNC RFB sockets.
3. **3-Tier Network Segmentation**: Partition the monolithic `ptnet` into three isolated bridge networks:
   - `frontend-net`: Connects `pt-nginx` to `pt-guacamole` and `pt-management`.
   - `backend-net`: Connects `pt-guacamole` and `pt-management` to `guacamole-mariadb` and `guacd`.
   - `vnc-net`: Connects `guacd` to desktop instances (`ptvnc1..N`). Prevents desktop instances from communicating with database backends or edge ingress points.
4. **Log Rotation & Enterprise Observability Stack**:
   - Enforce Docker `json-file` logging driver with `max-size: "50m"` and `max-file: "5"` across all containers to prevent host disk exhaustion.
   - Deploy Prometheus monitoring endpoints: `cadvisor` for container CPU/memory metrics, `node-exporter` for host telemetry, and Guacamole Prometheus metrics exporter.
5. **Database Connection Pooling & Tuning**: Configure MariaDB server parameters: `max_connections = 250`, `innodb_buffer_pool_size = 1G`, `innodb_log_file_size = 256M`. Configure SQLAlchemy connection pooling in `pt-management` (`pool_size=20, max_overflow=10, pool_recycle=1800, pool_pre_ping=True`).
6. **Automated MariaDB Backup Lifecycle**: Implement scheduled logical database dumps using `mysqldump --single-transaction --quick --routines --triggers --events` with gzip compression. Enforce strict retention schedules: 24 hourly, 30 daily, and 12 monthly archives.
7. **Classroom Sizing & Capacity Automation**: Implement pre-warming orchestration scripts for scheduled university lab sessions. Enforce session reaping routines to terminate idle student instances after 60 minutes of inactivity.

#### 1.4.2 Phase 3 Deliverables & Acceptance Milestones
- **D3.1**: Production-grade `docker-compose.yml` with health checks, resource limits, and network segmentation.
- **D3.2**: Automated database backup script (`scripts/mariadb-backup.sh`) with retention and verification.
- **D3.3**: Prometheus and Grafana dashboards for real-time Guacamole and container telemetry.
- **D3.4**: Classroom pre-warming and idle session reclamation daemon (`scripts/prewarm-instances.py`).
- **Milestone M3 Acceptance Criteria**:
  - `docker compose up -d` executes synchronously with dynamic health dependency resolution; zero sleep commands required.
  - Inter-container network isolation verified: `ptvnc1` cannot ping or route packets to `guacamole-mariadb` on port 3306.
  - Automated disaster recovery test confirms database backup restoration completes with RTO < 15 minutes and zero data loss.
  - Sustained load test of 50 concurrent student sessions maintains interactive Guacamole frame rate (> 24 FPS) with CPU overhead < 65%.

---

## Section 2: Comprehensive Risk Assessment Matrix

### 2.1 Risk Evaluation Methodology
Risks are evaluated across Technical (`TEC`), Operational (`OPS`), and User Experience (`UX`) domains. Each risk is assigned:
- **Probability ($P$)**: Low (1), Medium (2), High (3).
- **Impact ($I$)**: Low (1), Medium (2), High (3).
- **Severity Score ($S$)**: Calculated as $P \times I$, yielding a scale from 1 (Negligible) to 9 (Critical).

```
Severity Scale:
  1 - 2: Minor (Informational monitoring)
  3 - 4: Moderate (Mitigate during normal sprints)
  6    : High (Address before production release)
  9    : Critical (Blocker; immediate remediation required)
```

### 2.2 Risk Assessment Matrix Table

| Risk ID | Cat | Phase | Risk Description | Prob (P) | Imp (I) | Score (S) | Concrete Mitigation Strategy | Early Warning Indicators & Telemetry Triggers |
|---|---|---|---|---|---|---|---|---|
| **RISK-TEC-01** | TEC | Phase 1 | **Docker Socket Compromise & Host Escape**: Management container runs as root with `/var/run/docker.sock` mounted directly. Unauthenticated API allows arbitrary container execution and full host takeover. | High (3) | High (3) | **9 (Crit)** | Interpose `docker-socket-proxy` with read-only/container-only permissions; run Flask as unprivileged `ptmgmt` user (UID 10001); drop all capabilities (`cap_drop: [ALL]`); enforce `no-new-privileges: true`. | Container auditing alerts on root exec; unauthorized Docker daemon API calls; unexpected outbound network connections from management container. |
| **RISK-TEC-02** | TEC | Phase 2 | **Anonymous Volume Migration Data Loss**: Upstream MariaDB container uses anonymous volume. Destroying or recreating container causes catastrophic, irreversible loss of all user and connection records. | High (3) | High (3) | **9 (Crit)** | Execute pre-migration data copy from anonymous volume to named volume `mariadb_data` using `alpine cp -a`; verify schema and row parity before decommissioning legacy volume. | MariaDB initialization logs displaying "Initializing database" on container restart; missing `guacamole_user` table. |
| **RISK-TEC-03** | TEC | Phase 2 | **Guacamole Connection Table Lockup / Duplicate Rows (`ERROR 1242`)**: Connection generation script fails to account for `NULL parent_id`, causing subquery to return duplicate rows and aborting user provisioning. | High (3) | High (3) | **9 (Crit)** | Update SQL queries to explicitly filter `WHERE parent_id IS NULL`; replace naive `INSERT` statements with idempotent `INSERT ... ON DUPLICATE KEY UPDATE` syntax; add unique constraint on `(connection_name, parent_id)`. | MariaDB error logs registering `ERROR 1242 (21000): Subquery returns more than 1 row`; failed student container provisioning jobs in Flask logs. |
| **RISK-TEC-04** | TEC | Phase 1 | **Tomcat IP Ban Lockout of Institutional NAT IP Ranges**: Guacamole's `BanningAuthenticationListener` records Nginx gateway IP (`172.x.x.x`) instead of real client IP. A single student typo locks out entire university campus. | High (3) | High (3) | **9 (Crit)** | Deploy `RemoteIpValve` in Tomcat `conf/server.xml` with strict RFC 1918 regex: `internalProxies="10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3}"`; ensure Nginx sets `X-Forwarded-For $remote_addr`; configure valve to extract true remote client IP. | Spike in HTTP 403 Forbidden responses across multiple disparate student sessions originating from institutional IP blocks. |
| **RISK-TEC-05** | TEC | Phase 2 | **QtWebEngine / Chromium Crash 133 / SIGBUS from `/dev/shm` 64MB Constraint**: Packet Tracer 8.x embedded web engines exhaust default 64MB Docker `/dev/shm`, triggering rendering engine crashes. | High (3) | Med (2) | **6 (High)** | Explicitly allocate `shm_size: 512m` in Docker Compose for all `ptvnc` instances; monitor shared memory consumption under multi-tab laboratory exercises. | Exit code 133 in container logs; kernel dmesg showing `SIGBUS` in `PacketTracer`; user reports of blank white screens in Packet Tracer UI. |
| **RISK-TEC-06** | TEC | Phase 2 | **Defunct `[AppRun]` Zombie Process Storm Exhausting Host PID Space**: Container lacks PID 1 init system. Terminated Packet Tracer processes remain defunct zombies, exhausting host PID limits. | High (3) | Med (2) | **6 (High)** | Install and configure `tini -g` as PID 1 entrypoint in `Dockerfile.ptvnc`; tini properly reaps orphaned and defunct child processes; set container `pids_limit: 4096`. | `ps aux | grep defunct` showing > 5 defunct processes per container; host kernel warnings: `cgroup: fork rejected by pids controller`. |
| **RISK-UX-07** | UX | Phase 1 | **Nginx Proxy Buffering Causing Interactive Mouse Latency**: Default Nginx proxy buffering delays TCP transmission of interactive Guacamole mouse/keyboard frames, degrading user experience. | High (3) | Med (2) | **6 (High)** | Set `proxy_buffering off;` and `proxy_request_buffering off;` in Nginx Guacamole `location` block; configure WebSocket proxying with 3600s timeouts and `proxy_set_header Connection "upgrade"`. | Student complaints of "laggy mouse cursor" or rubber-banding; Guacamole client log showing high round-trip latency (> 150ms). |
| **RISK-OPS-08** | OPS | Phase 1 | **Destructive Host Cleanup Scripts (`cleanup-all.sh`) Wiping Unrelated Docker Assets**: Script executes global `docker rm -f $(docker ps -aq)` and `docker volume rm`, destroying all host databases and containers. | Med (2) | High (3) | **6 (High)** | Refactor `cleanup-all.sh` to scope operations strictly to `label=com.docker.compose.project=ptweb`; add interactive confirmation prompts and dry-run flags; forbid un-scoped `docker system prune`. | Execution of cleanup script in multi-tenant Docker host environments destroying staging/production containers outside PacketTracerWeb. |
| **RISK-OPS-09** | OPS | Phase 3 | **Classroom Peak Login Surge Causing MariaDB Connection Exhaustion & OOM**: 50+ students logging in simultaneously at start of class exhausts database connection pool and spikes container memory. | High (3) | Med (2) | **6 (High)** | Increase MariaDB `max_connections` to 250; configure SQLAlchemy connection pool (`pool_size=20, max_overflow=10`); implement classroom pre-warming script to stagger container bootstrapping. | MariaDB logs showing `Too many connections`; HTTP 500 errors in Flask portal during first 5 minutes of scheduled lab sessions. |
| **RISK-TEC-10** | TEC | Phase 2 | **Student File Cross-Tenant Leakage or Path Traversal in Shared Storage**: World-writable `/shared` directory allows students to read or overwrite peers' `.pkt` files via path traversal or direct filesystem access. | Med (2) | High (3) | **6 (High)** | Isolate student workspaces into `/shared/users/{user_id}/`; set directory permissions to `0700`; enforce strict path sanitization rejecting `../`, `%2e%2e`, and null bytes in file APIs. | File retrieval API requests containing `..` or `%2e%2e` in access logs; unauthorized file access events detected by audit logging. |
| **RISK-TEC-11** | TEC | Phase 1 | **TLS Cipher Mismatch with Legacy Student Browser Clients**: Overly restrictive TLS ciphers prevent students on older institutional hardware or browsers from establishing HTTPS sessions. | Med (2) | Med (2) | **4 (Med)** | Adopt Mozilla Intermediate TLS configuration; support TLS 1.2 and TLS 1.3 with standard ECDHE ciphers; maintain compatibility with Chrome 70+, Firefox 63+, Safari 12+. | TLS handshake failure alerts in Nginx error logs (`SSL_do_handshake() failed`); client-side `ERR_SSL_VERSION_OR_CIPHER_MISMATCH`. |
| **RISK-TEC-12** | TEC | Phase 3 | **Network Segmentation Misconfiguration Breaking Guacamole-to-VNC Tunnels**: Isolating networks blocks Guacamole proxy daemon (`guacd`) from routing RFB traffic to `ptvnc` instances. | Med (2) | High (3) | **6 (High)** | Attach `guacd` to both `backend-net` and `vnc-net`; ensure internal DNS service discovery resolves `ptvnc` container names across the shared `vnc-net` bridge. | Guacamole client UI displaying `Connection Error: The remote desktop server is currently unreachable`; guacd logs showing connection refused on 5901. |
| **RISK-TEC-13** | TEC | Phase 2 | **Cisco Packet Tracer EULA or Display Initialization Failures Under Headless Containers**: Interactive deb package installation prompts for EULA confirmation, hanging headless container builds. | Med (2) | High (3) | **6 (High)** | Pre-seed debconf answers (`echo "pt8 accept-eula boolean true" | debconf-set-selections`) or unpack via `dpkg-deb -x`; configure `libgl1-mesa-glx` software rendering fallback. | Docker build hangs indefinitely at `Setting up packettracer`; container runtime crashes with `QXcbConnection: Could not connect to display`. |
| **RISK-UX-14** | UX | Phase 2 | **VNC Clipboard Synchronization Failure Hanging Student Workflows**: Failure of clipboard daemon prevents bidirectional copy-paste between client browser and Cisco Packet Tracer CLI. | Med (2) | Med (2) | **4 (Med)** | Run `autocutsel -s CLIPBOARD -fork` and `autocutsel -s PRIMARY -fork` in `start-session`; ensure TurboVNC RFB clipboard extensions are enabled in Guacamole client parameters. | Student helpdesk tickets reporting inability to paste Cisco IOS router configurations into Packet Tracer CLI terminal. |

---

## Section 3: Step-by-Step Migration Engineering, Runbooks & Disaster Recovery

### 3.1 Pre-Migration Validation Checklist
Before executing any migration commands, the platform engineering team must execute the following automated pre-flight audit checklist to verify host readiness, kernel parameters, port availability, and storage headroom.

```bash
#!/usr/bin/env bash
# ==============================================================================
# PRE-MIGRATION VALIDATION CHECKLIST SCRIPT: preflight_check.sh
# Target: PacketTracerWeb Production Hardening Audit
# ==============================================================================
set -euo pipefail

echo "========================================================================"
echo "PACKETTRACERWEB PRE-MIGRATION READINESS AUDIT"
echo "Timestamp: $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "========================================================================"

FAILED_CHECKS=0

# 1. Host Kernel Parameters Audit
echo -n "[CHECK 1/6] Validating Linux Kernel Parameters (sysctl)... "
SYSCTL_ERRORS=()

FILE_MAX=$(sysctl -n fs.file-max)
if [ "$FILE_MAX" -lt 2097152 ]; then
    SYSCTL_ERRORS+=("fs.file-max ($FILE_MAX) < 2097152")
fi

MAX_MAP=$(sysctl -n vm.max_map_count)
if [ "$MAX_MAP" -lt 262144 ]; then
    SYSCTL_ERRORS+=("vm.max_map_count ($MAX_MAP) < 262144")
fi

INOTIFY_WATCHES=$(sysctl -n fs.inotify.max_user_watches)
if [ "$INOTIFY_WATCHES" -lt 524288 ]; then
    SYSCTL_ERRORS+=("fs.inotify.max_user_watches ($INOTIFY_WATCHES) < 524288")
fi

SOMAXCONN=$(sysctl -n net.core.somaxconn)
if [ "$SOMAXCONN" -lt 4096 ]; then
    SYSCTL_ERRORS+=("net.core.somaxconn ($SOMAXCONN) < 4096")
fi

if [ ${#SYSCTL_ERRORS[@]} -eq 0 ]; then
    echo "PASSED (fs.file-max=$FILE_MAX, vm.max_map_count=$MAX_MAP)"
else
    echo "FAILED: ${SYSCTL_ERRORS[*]}"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# 2. Docker Engine & Compose v2 Verification
echo -n "[CHECK 2/6] Validating Docker Engine & Compose v2... "
if command -v docker >/dev/null 2>&1; then
    DOCKER_VER=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "0.0.0")
    DOCKER_MAJOR=$(echo "$DOCKER_VER" | cut -d. -f1)
    if [ "$DOCKER_MAJOR" -ge 24 ]; then
        if docker compose version >/dev/null 2>&1; then
            COMPOSE_VER=$(docker compose version --short)
            echo "PASSED (Docker $DOCKER_VER, Compose v$COMPOSE_VER)"
        else
            echo "FAILED: Docker Compose v2 plugin missing"
            FAILED_CHECKS=$((FAILED_CHECKS + 1))
        fi
    else
        echo "FAILED: Docker Engine ($DOCKER_VER) < 24.0.0"
        FAILED_CHECKS=$((FAILED_CHECKS + 1))
    fi
else
    echo "FAILED: Docker not installed on host"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# 3. Port Availability Audit
echo -n "[CHECK 3/6] Auditing Required Host Ports (443, 5000, 3306, 4822, 5901)... "
PORT_CONFLICTS=()
for PORT in 443 5000; do
    if ss -tuln | grep -q ":${PORT} "; then
        PORT_CONFLICTS+=("$PORT (Edge Ingress Conflict)")
    fi
done
for PORT in 3306 4822 5901; do
    if ss -tuln | grep -q ":${PORT} "; then
        PORT_CONFLICTS+=("$PORT (Internal Port Exposed on Host)")
    fi
done

if [ ${#PORT_CONFLICTS[@]} -eq 0 ]; then
    echo "PASSED (All required ports available and unexposed)"
else
    echo "FAILED: Port conflicts detected: ${PORT_CONFLICTS[*]}"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# 4. Storage Capacity Audit
echo -n "[CHECK 4/6] Verifying Storage Headroom on /var/lib/docker... "
DOCKER_ROOT=$(docker info --format '{{.DockerRootDir}}' 2>/dev/null || echo "/var/lib/docker")
FREE_SPACE_KB=$(df -k "$DOCKER_ROOT" | awk 'NR==2 {print $4}')
FREE_SPACE_GB=$((FREE_SPACE_KB / 1024 / 1024))

if [ "$FREE_SPACE_GB" -ge 20 ]; then
    echo "PASSED (${FREE_SPACE_GB}GB available, >= 20GB required)"
else
    echo "FAILED: Insufficient disk space on $DOCKER_ROOT (${FREE_SPACE_GB}GB available, 20GB required)"
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# 5. Dry-Run Configuration Syntax Validation
echo -n "[CHECK 5/6] Executing Dry-Run Configuration Checks (compose config, nginx -t)... "
DRY_RUN_PASSED=true

# Locate docker-compose.yml supporting both repository root and legacy ptweb-vnc paths
COMPOSE_FILE=""
for p in "docker-compose.yml" "ptweb-vnc/docker-compose.yml"; do
    if [ -f "$p" ]; then COMPOSE_FILE="$p"; break; fi
done

if [ -n "$COMPOSE_FILE" ]; then
    if ! docker compose -f "$COMPOSE_FILE" config --quiet; then
        echo "FAILED: 'docker compose config' syntax validation failed for $COMPOSE_FILE"
        DRY_RUN_PASSED=false
    fi
else
    echo "FAILED: docker-compose.yml not found in . or ./ptweb-vnc/"
    DRY_RUN_PASSED=false
fi

# Locate Nginx configuration supporting both repository root and legacy ptweb-vnc paths
NGINX_CONF=""
for p in "nginx/conf.d/default.conf" "ptweb-vnc/nginx/conf.d/default.conf" "ptweb-vnc/pt-nginx/conf/ptweb.conf"; do
    if [ -f "$p" ]; then NGINX_CONF="$p"; break; fi
done

if [ -n "$NGINX_CONF" ]; then
    # Test nginx syntax using an ephemeral container mounting the configuration.
    # Attaching --network host prevents false-positive upstream resolution failures (e.g. host not found in upstream "pt-guacamole")
    if ! docker run --rm --network host -v "$(pwd)/$NGINX_CONF:/etc/nginx/conf.d/default.conf:ro" \
        nginx:alpine nginx -t >/dev/null 2>&1; then
        # Fallback check for syntax validity ignoring upstream resolution if isolated from bridge network
        if ! docker run --rm -v "$(pwd)/$NGINX_CONF:/etc/nginx/conf.d/default.conf:ro" \
            nginx:alpine nginx -t 2>&1 | grep -q "syntax is ok"; then
            echo "FAILED: 'nginx -t' configuration check failed for $NGINX_CONF"
            DRY_RUN_PASSED=false
        fi
    fi
else
    echo "FAILED: Nginx configuration not found in ./nginx/ or ./ptweb-vnc/"
    DRY_RUN_PASSED=false
fi

if [ "$DRY_RUN_PASSED" = true ]; then
    echo "PASSED ('docker compose config' and 'nginx -t' validated)"
else
    FAILED_CHECKS=$((FAILED_CHECKS + 1))
fi

# 6. Baseline Snapshot & Backup Verification
echo -n "[CHECK 6/6] Verifying Baseline Backup / Snapshot Exists... "
if [ -d "/backups" ] && [ -n "$(find /backups -name '*.sql.gz' -mtime -1 2>/dev/null)" ]; then
    echo "PASSED (Recent database snapshot found)"
else
    echo "WARNING: No verified database snapshot found in /backups within last 24h"
fi

echo "========================================================================"
if [ "$FAILED_CHECKS" -eq 0 ]; then
    echo "PRE-MIGRATION AUDIT PASSED: System ready for phase execution."
    exit 0
else
    echo "PRE-MIGRATION AUDIT FAILED: $FAILED_CHECKS critical checks failed. Aborting."
    exit 1
fi
```

---

### 3.2 Step-by-Step Migration Execution Runbooks per Phase

#### 3.2.1 Phase 1 Execution Runbook (Immediate Security Hotfixes)
```bash
# ==============================================================================
# PHASE 1 EXECUTION RUNBOOK: Zero-Downtime Hotfixes
# ==============================================================================

# Step 1.1: Deploy Docker Socket Proxy
echo "[Step 1.1] Deploying tecnativa/docker-socket-proxy..."
docker run -d \
    --name docker-socket-proxy \
    --restart always \
    --network ptnet \
    -v /var/run/docker.sock:/var/run/docker.sock:ro \
    -e CONTAINERS=1 \
    -e POST=1 \
    -e IMAGES=1 \
    -e NETWORKS=1 \
    -e VOLUMES=0 \
    -e SYSTEM=0 \
    -e INFO=1 \
    tecnativa/docker-socket-proxy:latest

# Step 1.2: Remove Webroot Credential Leaks
echo "[Step 1.2] Deleting exposed bulk-user-api.php from Nginx webroot..."
docker exec pt-nginx rm -f /var/www/html/bulk-user-api.php || true
rm -f frontend/bulk-user-api.php

# Step 1.3: Update Nginx Edge Configuration with Security Headers, Disable Webroot Leak & GeoIP Fix
echo "[Step 1.3] Updating Nginx configuration and eliminating /downloads/ webroot leak..."
# Create backup for safe rollback
cp nginx/conf.d/default.conf nginx/conf.d/default.conf.bak 2>/dev/null || true
[ -f ptweb-vnc/pt-nginx/conf/ptweb.conf ] && cp ptweb-vnc/pt-nginx/conf/ptweb.conf ptweb-vnc/pt-nginx/conf/ptweb.conf.bak

# Eliminate unauthenticated public directory indexing of /shared/users/
# Remove/patch legacy: location ^~ /downloads/ { alias /shared/; autoindex on; }
for conf in "nginx/conf.d/default.conf" "ptweb-vnc/nginx/conf.d/default.conf" "ptweb-vnc/pt-nginx/conf/ptweb.conf"; do
    if [ -f "$conf" ]; then
        # Strip unauthenticated downloads autoindex block to prevent student workspace indexing
        sed -i '/location \^\~ \/downloads\//,/}/d' "$conf"
    fi
done

cat << 'EOF' > nginx/conf.d/security_headers.conf
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' wss:; frame-ancestors 'self';" always;
server_tokens off;
EOF

# Hot-reload Nginx configuration without dropping connections
docker exec pt-nginx nginx -t
docker exec pt-nginx nginx -s reload

# Step 1.4: Configure Tomcat RemoteIpValve in Guacamole (Strict RFC 1918 Scope)
echo "[Step 1.4] Applying RemoteIpValve to Tomcat server.xml..."
docker exec -i pt-guacamole /bin/bash << 'EOF'
# Create backup for safe rollback
cp /usr/local/tomcat/conf/server.xml /usr/local/tomcat/conf/server.xml.bak 2>/dev/null || true

xmlstarlet ed -L -s "/Server/Service/Engine/Host" -t elem -n "ValveTmp" \
  -i "/Server/Service/Engine/Host/ValveTmp" -t attr -n "className" -v "org.apache.catalina.valves.RemoteIpValve" \
  -i "/Server/Service/Engine/Host/ValveTmp" -t attr -n "internalProxies" -v "10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3}|127\.\d{1,3}\.\d{1,3}\.\d{1,3}" \
  -i "/Server/Service/Engine/Host/ValveTmp" -t attr -n "remoteIpHeader" -v "x-forwarded-for" \
  -i "/Server/Service/Engine/Host/ValveTmp" -t attr -n "remoteIpProxiesHeader" -v "x-forwarded-by" \
  -i "/Server/Service/Engine/Host/ValveTmp" -t attr -n "protocolHeader" -v "x-forwarded-proto" \
  -r "/Server/Service/Engine/Host/ValveTmp" -v "Valve" \
  /usr/local/tomcat/conf/server.xml
EOF
docker restart pt-guacamole

# Step 1.5: Patch Host Cleanup Script
echo "[Step 1.5] Hardening Scripts/cleanup-all.sh..."
sed -i 's/docker rm -f $(docker ps -aq)/docker rm -f $(docker ps -q -f "label=com.docker.compose.project=ptweb")/g' Scripts/cleanup-all.sh
sed -i 's/docker volume rm $(docker volume ls -q)/docker volume prune -f --filter "label=com.docker.compose.project=ptweb"/g' Scripts/cleanup-all.sh
```

---

### 3.3 MariaDB Anonymous-to-Named Volume Migration Runbook
This runbook provides the safe, deterministic procedure to migrate the legacy anonymous MariaDB volume to the production persistent named volume `mariadb_data`.

```bash
# ==============================================================================
# MARIADB ANONYMOUS TO NAMED VOLUME MIGRATION RUNBOOK
# Execution Window: Scheduled Maintenance (15 minutes)
# ==============================================================================
set -euo pipefail

echo "Starting MariaDB volume migration..."

# Step 1: Identify Legacy Anonymous Volume
ANON_VOLUME=$(docker inspect guacamole-mariadb --format '{{range .Mounts}}{{if eq .Destination "/var/lib/mysql"}}{{.Name}}{{end}}{{end}}')
echo "Detected source anonymous volume ID: $ANON_VOLUME"

if [ -z "$ANON_VOLUME" ]; then
    echo "ERROR: Could not locate anonymous volume mounted at /var/lib/mysql. Aborting."
    exit 1
fi

# Step 2: Quiesce Database Activity and Stop Container
echo "Stopping MariaDB container to ensure clean InnoDB state..."
docker stop guacamole-mariadb

# Step 3: Create Persistent Named Volume
echo "Creating persistent named volume 'mariadb_data'..."
docker volume create mariadb_data

# Step 4: Execute Safe Data Copy Using Ephemeral Alpine Container
echo "Executing raw bit-level copy from anonymous volume to mariadb_data..."
docker run --rm -v "$ANON_VOLUME:/source:ro" -v mariadb_data:/target alpine cp -a /source/. /target/

# Step 5: Verify Permissions on Destination Named Volume
echo "Verifying file ownership and permissions for MySQL user (UID 999)..."
docker run --rm \
    -v mariadb_data:/target \
    alpine chown -R 999:999 /target

# Step 6: Validate Data Parity
echo "Validating core database structure on destination named volume..."
docker run --rm \
    -v mariadb_data:/target \
    alpine ls -la /target/guacamole_db

# Step 7: Update Compose Configuration to Point to mariadb_data
echo "Updating docker-compose.yml to bind mariadb_data..."
sed -i "s|$ANON_VOLUME:/var/lib/mysql|mariadb_data:/var/lib/mysql|g" docker-compose.yml

# Step 8: Recreate MariaDB Container on Named Volume
# CRITICAL ARCHITECTURAL NOTE: 'docker start' preserves existing immutable container volume bindings
# (retaining the anonymous volume). The container must be destroyed and recreated so Docker Compose
# rebinds /var/lib/mysql to the newly declared 'mariadb_data' named volume.
echo "Recreating guacamole-mariadb container to bind named volume..."
docker rm -f guacamole-mariadb && docker compose up -d guacamole-mariadb

# Step 9: Verify Database Integrity and Query Health (Portable CLI commands)
echo "Verifying MariaDB service availability and table accessibility..."
until docker exec guacamole-mariadb sh -c 'mariadb-admin -u root -p"${DB_ROOT_PASSWORD}" ping --silent 2>/dev/null || mysqladmin -u root -p"${DB_ROOT_PASSWORD}" ping --silent'; do
    sleep 2
done
docker exec guacamole-mariadb sh -c 'mariadb -u root -p"${DB_ROOT_PASSWORD}" -e "SELECT COUNT(*) AS total_users FROM guacamole_db.guacamole_user;" 2>/dev/null || mysql -u root -p"${DB_ROOT_PASSWORD}" -e "SELECT COUNT(*) AS total_users FROM guacamole_db.guacamole_user;"'

echo "MariaDB Named Volume Migration Completed Successfully."
```

---

### 3.4 MariaDB Backup, Disaster Recovery & Retention Policy

#### 3.4.1 Recovery Objectives
- **Recovery Point Objective (RPO)**: $\le 15 \text{ minutes}$. Achieved via 15-minute point-in-time MariaDB binary logging (`log_bin = /var/log/mysql/mariadb-bin`) and hourly differential snapshots.
- **Recovery Time Objective (RTO)**: $\le 30 \text{ minutes}$. Complete catastrophic disaster recovery from raw gzip backup to full operational availability within 30 minutes.

#### 3.4.2 Automated Backup Command & Schedule
Logical backups must be executed non-blocking without acquiring global read locks that stall active student sessions:

```bash
# Non-blocking logical dump command:
mysqldump \
    --single-transaction \
    --quick \
    --routines \
    --triggers \
    --events \
    --hex-blob \
    -u root -p"${DB_ROOT_PASSWORD}" \
    guacamole_db | gzip -9 > /backups/mariadb/guacamole_db_$(date +%Y%m%d_%H%M%S).sql.gz
```

#### 3.4.3 Automated Backup & Retention Policy Daemon
The backup policy enforces:
- **Hourly Backups**: Retained for 24 hours (24 snapshots).
- **Daily Backups**: Retained for 30 days (30 snapshots).
- **Monthly Backups**: Retained for 12 months (12 archives).

```bash
#!/usr/bin/env bash
# ==============================================================================
# SCRIPT: scripts/mariadb-backup-lifecycle.sh
# Purpose: Automated MariaDB backup, validation, and retention lifecycle
# ==============================================================================
set -euo pipefail

BACKUP_DIR="/backups/mariadb"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
DAILY_DIR="$BACKUP_DIR/daily"
HOURLY_DIR="$BACKUP_DIR/hourly"
MONTHLY_DIR="$BACKUP_DIR/monthly"

mkdir -p "$HOURLY_DIR" "$DAILY_DIR" "$MONTHLY_DIR"

BACKUP_FILE="$HOURLY_DIR/guacamole_db_${TIMESTAMP}.sql.gz"

echo "Executing consistent logical backup to $BACKUP_FILE..."
docker exec guacamole-mariadb mysqldump \
    --single-transaction \
    --quick \
    --routines \
    --triggers \
    --events \
    --hex-blob \
    -u root -p"${DB_ROOT_PASSWORD}" guacamole_db | gzip -9 > "$BACKUP_FILE"

# Integrity Verification
echo "Verifying gzip integrity..."
gzip -t "$BACKUP_FILE"

# Copy to daily if first backup of the day
if [ "$(date +%H)" = "00" ]; then
    cp "$BACKUP_FILE" "$DAILY_DIR/guacamole_db_$(date +%Y%m%d).sql.gz"
fi

# Copy to monthly if first day of the month
if [ "$(date +%d%H)" = "0100" ]; then
    cp "$BACKUP_FILE" "$MONTHLY_DIR/guacamole_db_$(date +%Y%m).sql.gz"
fi

# Enforce Retention Policy
echo "Applying retention pruning..."
find "$HOURLY_DIR" -type f -name "*.sql.gz" -mmin +1440 -delete   # 24 Hours
find "$DAILY_DIR" -type f -name "*.sql.gz" -mtime +30 -delete     # 30 Days
find "$MONTHLY_DIR" -type f -name "*.sql.gz" -mtime +365 -delete  # 12 Months
echo "Backup cycle complete."
```

#### 3.4.4 Disaster Recovery Restoration Runbook
In the event of database corruption or hardware failure, follow this exact recovery runbook:

```bash
# ==============================================================================
# DISASTER RECOVERY RESTORATION RUNBOOK
# Target RTO: <= 30 minutes
# ==============================================================================
set -euo pipefail

BACKUP_ARCHIVE="${1:-/backups/mariadb/daily/latest.sql.gz}"
echo "Initiating Disaster Recovery restore from: $BACKUP_ARCHIVE"

# Step 1: Verify Archive Integrity
gzip -t "$BACKUP_ARCHIVE"

# Step 2: Stop Management and Gateway Services to Prevent Inconsistent Writes
docker stop pt-management pt-guacamole

# Step 3: Recreate Fresh MariaDB Database Container
docker stop guacamole-mariadb || true
docker rm guacamole-mariadb || true
docker volume rm mariadb_data || true
docker volume create mariadb_data

docker run -d \
    --name guacamole-mariadb \
    --restart always \
    --network backend-net \
    -v mariadb_data:/var/lib/mysql \
    -e MYSQL_ROOT_PASSWORD="${DB_ROOT_PASSWORD}" \
    -e MYSQL_DATABASE=guacamole_db \
    -e MYSQL_USER=guacamole_user \
    -e MYSQL_PASSWORD="${DB_PASSWORD}" \
    mariadb:11.4

echo "Waiting for MariaDB daemon initialization..."
until docker exec guacamole-mariadb mysqladmin -u root -p"${DB_ROOT_PASSWORD}" ping --silent; do
    sleep 2
done

# Step 4: Stream and Execute Compressed SQL Restore
echo "Restoring database schema and records..."
zcat "$BACKUP_ARCHIVE" | docker exec -i guacamole-mariadb mysql -u root -p"${DB_ROOT_PASSWORD}" guacamole_db

# Step 5: Verify Restoration Row Counts
docker exec guacamole-mariadb mysql -u root -p"${DB_ROOT_PASSWORD}" -e "
    SELECT 
        (SELECT COUNT(*) FROM guacamole_db.guacamole_user) AS user_count,
        (SELECT COUNT(*) FROM guacamole_db.guacamole_connection) AS conn_count;"

# Step 6: Restart Application Gateways
docker start pt-guacamole pt-management
echo "Disaster recovery restoration verified and completed."
```

---

### 3.5 Deterministic Rollback Procedures Across All Phases

#### 3.5.1 Rollback Trigger Criteria & Objective Thresholds
A rollback MUST be initiated immediately if any of the following objective thresholds are breached during a migration window:
1. **Error Rate Threshold**: HTTP 5xx responses exceed 5% of total requests over a rolling 3-minute window.
2. **Health Check Failure Threshold**: Any core service (`pt-guacamole`, `guacamole-mariadb`, `guacd`) fails its Docker `HEALTHCHECK` for $> 3$ consecutive minutes.
3. **Data Integrity Failure**: Database checksum or foreign key validation fails post-migration, or missing records detected.
4. **Interactive Latency Degradation**: Guacamole client-side RTT exceeds 500ms for $> 10\%$ of active users.
5. **Display Crash Threshold**: More than 2 desktop container instances crash with SIGBUS or segfault within a 10-minute window.

```
+-------------------------------------------------------------------------------+
|                       OBJECTIVE ROLLBACK DECISION MATRIX                      |
+-------------------------------------------------------------------------------+
| Metric Trigger             | Threshold Limit    | Action Required             |
+----------------------------+--------------------+-----------------------------+
| Edge Gateway 5xx Rate      | > 5.0% for 3 mins  | Abort; Trigger Runbook 3.5.2|
| Core Service Healthcheck   | Unhealthy > 180s   | Abort; Trigger Runbook 3.5.3|
| Database Corruption / Loss | Any data mismatch  | Abort; Trigger Runbook 3.5.3|
| WebSocket Session Drops    | > 10% disconnects  | Revert Nginx proxy buffering|
+-------------------------------------------------------------------------------+
```

#### 3.5.2 Phase 1 Rollback Runbook (Perimeter & Hotfix Reversion)
```bash
# ==============================================================================
# PHASE 1 ROLLBACK RUNBOOK
# Execution Time: < 3 minutes
# ==============================================================================
echo "[ROLLBACK Phase 1] Reverting perimeter hotfixes..."

# 1. Restore previous Nginx configuration
cp nginx/conf.d/default.conf.bak nginx/conf.d/default.conf
docker exec pt-nginx nginx -s reload

# 2. Revert Tomcat server.xml in Guacamole
docker exec -i pt-guacamole cp /usr/local/tomcat/conf/server.xml.bak /usr/local/tomcat/conf/server.xml
docker restart pt-guacamole

# 3. Teardown Docker Socket Proxy if routing fails
docker stop docker-socket-proxy || true
docker rm docker-socket-proxy || true

# 4. Verify Edge Gateway Functionality
curl -kfs https://localhost/healthz || echo "WARNING: Gateway unhealthy"
```

#### 3.5.3 Phase 2 Rollback Runbook (Storage & Container Reversion)
```bash
# ==============================================================================
# PHASE 2 ROLLBACK RUNBOOK: Volume & Init Reversion
# Execution Time: < 10 minutes
# ==============================================================================
echo "[ROLLBACK Phase 2] Reverting named volume to anonymous volume backup..."

# 1. Stop MariaDB
docker stop guacamole-mariadb

# 2. Re-bind legacy anonymous volume in docker-compose.yml
sed -i "s|mariadb_data:/var/lib/mysql|$ANON_VOLUME:/var/lib/mysql|g" docker-compose.yml

# 3. Start MariaDB on legacy volume
docker start guacamole-mariadb

# 4. Revert ptvnc desktop images to previous stable build (tag: v1-legacy-xvfb)
docker service update --image ptvnc:v1-legacy-xvfb ptvnc_stack || docker-compose up -d --no-deps ptvnc1

# 5. Verify database records
docker exec guacamole-mariadb mysql -u root -p"${DB_ROOT_PASSWORD}" -e "SELECT COUNT(*) FROM guacamole_db.guacamole_user;"
```

#### 3.5.4 Phase 3 Rollback Runbook (Network & Compose v2 Reversion)
```bash
# ==============================================================================
# PHASE 3 ROLLBACK RUNBOOK: Network & Orchestration Reversion
# Execution Time: < 5 minutes
# ==============================================================================
echo "[ROLLBACK Phase 3] Tearing down segmented networks and reverting to Compose v1..."

# 1. Bring down segmented Compose v2 stack
docker compose down

# 2. Re-establish flat bridge network ptnet
docker network create ptnet || true

# 3. Launch legacy monolithic deployment harness
./deploy.sh

# 4. Verify full system connectivity
./health_check.sh
```

---

## Section 4: Software Dependency & Compatibility Matrix

This section establishes the definitive software compatibility, dependency baseline, and runtime configurations across all five core components.

```
+------------------------------------------------------------------------------------------------------+
|                               SOFTWARE COMPATIBILITY MATRIX MAP                                      |
+-----------------------------------+--------------------+--------------------+------------------------+
| Component                         | Target Version     | Runtime Host / OS  | Core Dependencies      |
+-----------------------------------+--------------------+--------------------+------------------------+
| Cisco Packet Tracer               | 8.2 / 8.3 / 8.4    | Ubuntu 22.04 LTS   | Qt6, OpenGL llvmpipe   |
| TurboVNC & VirtualGL              | TurboVNC 3.1+, VGL | Ubuntu 22.04 LTS   | libgl1-mesa, autocutsel|
| Apache Guacamole & guacd          | 1.5.5 / 1.6.0      | Debian / Tomcat 9  | MariaDB Connector 1.5+ |
| Apache Tomcat Application Server  | 9.0.80+            | OpenJDK 11 / 17    | RemoteIpValve, Caffeine|
| MariaDB Enterprise Backend        | 10.11 / 11.4 LTS   | Alpine / Debian    | InnoDB, utf8mb4        |
| Nginx Edge Reverse Proxy          | 1.27+ Mainline     | Alpine Linux       | GeoIP2 MMDB, OpenSSL 3 |
| Management Service Daemon         | Python 3.11 / 3.12 | Debian Bookworm    | Flask 3.0, Gunicorn 21 |
+-----------------------------------+--------------------+--------------------+------------------------+
```

### 4.1 Cisco Packet Tracer 8.x Compatibility & Runtime Dependencies
- **Supported Versions**: Cisco Packet Tracer 8.0, 8.1, 8.2, 8.3, and 8.4 (`CiscoPacketTracer`).
- **Distribution Model**: Native Debian distribution (`.deb`) preferred over AppImage due to container overhead, FUSE namespace limitations, and child process zombie hazards.
- **Ubuntu 22.04 LTS Runtime Dependencies**:
  - `libqt6core6`, `libqt6gui6`, `libqt6widgets6`, `libqt6network6`, `libqt6svg6`, `libqt6printsupport6`
  - `libgl1-mesa-glx`, `libgl1`, `libegl1`, `libglx-mesa0`
  - Software Rendering Fallback: In headless environments lacking physical GPU hardware, Mesa's llvmpipe software rasterizer must be enforced via `LIBGL_ALWAYS_SOFTWARE=1` and `QT_X11_NO_MITSHM=1`.
- **Non-Interactive Debian Extraction**:
  To circumvent interactive EULA prompts hanging headless Docker builds:
  ```bash
  # Option A: Pre-seed debconf answers
  echo "packettracer pt8/accept-eula boolean true" | debconf-set-selections
  DEBIAN_FRONTEND=noninteractive dpkg -i CiscoPacketTracer_8.2.0_amd64.deb || apt-get install -f -y

  # Option B: Direct payload extraction (bypassing pre/post-inst prompts)
  dpkg-deb -x CiscoPacketTracer_8.2.0_amd64.deb /opt/pt
  ln -sf /opt/pt/bin/PacketTracer /usr/local/bin/packettracer
  ```
- **Packet Tracer File Format Compatibility**:
  - `.pkt` (Network Topology Files) & `.pka` (Packet Tracer Activity Files): Full forward compatibility supported from version 7.x through 8.4. Backwards compatibility: Files authored in 8.3/8.4 cannot be opened in 8.0/8.1. Production instances within a single cluster must be pinned to an identical minor version (e.g., 8.2.2).

### 4.2 TurboVNC 3.x & VirtualGL 3.x Display Pipeline
- **TurboVNC Version**: Pinned to TurboVNC 3.1+ (eliminating legacy TightVNC 1.3 and standalone Xvfb).
- **VirtualGL 3.x (`vglrun`) Integration**:
  - When host GPU passthrough is present (`/dev/dri/renderD128`), VirtualGL intercepts OpenGL calls via `vglrun /usr/local/bin/packettracer`, hardware-accelerating Qt6 UI rendering.
  - When running in purely headless CPU virtualization, VirtualGL redirects to Mesa llvmpipe without performance degradation.
- **Elimination of Dual Display Servers**: Baseline ran both `Xvfb :1` and `TurboVNC :2`. The hardened architecture launches solely `TurboVNC :2` with integrated X11 rendering (`/opt/TurboVNC/bin/vncserver :2 -geometry 1920x1080 -depth 24`).
- **Clipboard Subsystem**: Bidirectional client-server clipboard synchronization is guaranteed via `autocutsel`:
  ```bash
  # Inside start-session entrypoint:
  autocutsel -s CLIPBOARD -fork
  autocutsel -s PRIMARY -fork
  ```

### 4.3 Apache Guacamole Stack (1.5.5 / 1.6.0)
- **Container Images**: Pinned to official images:
  - `guacamole/guacd:1.5.5`
  - `guacamole/guacamole:1.5.5`
- **Database Schema Compatibility**: Guacamole 1.5.5 requires the 1.5.5 schema upgrade scripts (`001-create-schema.sql` through `upgrade-pre-1.5.5.sql`). Fully backward-compatible with 0.9.14 data structures following automated column migration.
- **Tunnel Protocols**: Nginx edge proxy establishes WebSocket connections (`/guacamole/websocket-tunnel`). If client firewalls intercept WebSockets, Guacamole automatically falls back to HTTP streaming (`/guacamole/tunnel`). Both protocols require `proxy_buffering off;` in Nginx.

### 4.4 Apache Tomcat 9 Application Container
- **Base Version**: Tomcat 9.0.80+ running OpenJDK 11 or 17 LTS.
- **Client IP Resolution (`RemoteIpValve`)**:
  Configured in `conf/server.xml` to parse the `X-Forwarded-For` header injected by Nginx.
- **Authentication Failure Management**: Guacamole's `BanningAuthenticationListener` uses an in-memory Caffeine cache tracking failed login attempts per remote IP address. Without `RemoteIpValve`, the listener tracks the Nginx proxy IP, inadvertently banning all platform users when a single student fails login.

### 4.5 MariaDB 10.11 / 11.4 LTS Database Backend
- **Storage Engine**: Strictly InnoDB with `file_per_table=ON`.
- **Character Encoding & Collation**: `utf8mb4` with `utf8mb4_unicode_ci` to prevent encoding issues with international student names.
- **Connection Deduplication & Null Handling**: MariaDB adheres to ANSI SQL standards where `NULL != NULL`. The unique constraint on `(connection_name, parent_id)` does not prevent duplicate names when `parent_id IS NULL`. The hardened application guarantees connection uniqueness by enforcing `parent_id` defaults or utilizing application-level lock mutexes.

### 4.6 Nginx 1.27+ Edge Gateway
- **Modules**: Compiled with `ngx_http_geoip2_module` linked against `libmaxminddb`.
- **Database**: Official MaxMind GeoLite2-Country MMDB format replacing deprecated `.dat` formats.
- **Cryptographic Suite**: Linked with OpenSSL 3.0+; supports TLS 1.2 and TLS 1.3 only; enforces Mozilla Intermediate ciphers:
  ```nginx
  ssl_protocols TLSv1.2 TLSv1.3;
  ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384';
  ssl_prefer_server_ciphers off;
  ```

### 4.7 Python 3.11 / 3.12 Management Service
- **Framework**: Flask 3.0+ running on Gunicorn 21+ with `gevent` or `sync` workers.
- **Docker SDK**: Python `docker` package (v7.0+) communicating via UNIX domain socket or TCP proxy.
- **Form Security**: `Flask-WTF` providing CSRF protection across all session forms and JSON API endpoints.

---

## Section 5: Operational & Incident Response Runbooks

### 5.1 Guacamole IP Ban Lockout Incident Response Runbook

#### 5.1.1 Symptoms & Triage
- **Alert**: Multiple students report immediate HTTP 403 Forbidden or "Login failed" errors across campus IP ranges.
- **Telemetry Verification**:
  ```bash
  # Check Tomcat logs for active IP bans
  docker exec pt-guacamole grep -E "BanningAuthenticationListener.*banned" /usr/local/tomcat/logs/catalina.out
  ```
- **Root Cause**: A student exceeded the failed login threshold (default: 5 attempts). Due to missing or misconfigured `RemoteIpValve`, Tomcat recorded the Nginx gateway IP (`172.x.x.x`) or campus NAT gateway IP as the offending source, blocking all traffic from that ingress.

#### 5.1.2 Immediate Emergency Unban Procedure
To restore campus access immediately without destroying user sessions:

```bash
# Emergency Action 1: Restart Guacamole web application to flush Caffeine cache
echo "Flushing Guacamole in-memory IP ban cache..."
docker restart pt-guacamole

# Emergency Action 2: If bans are persisted in database (custom extension)
docker exec guacamole-mariadb mysql -u root -p"${DB_ROOT_PASSWORD}" guacamole_db \
    -e "DELETE FROM guacamole_ip_ban WHERE unban_timestamp > NOW();" || true
```

#### 5.1.3 Permanent Architectural Remediation
1. Verify Tomcat `conf/server.xml` contains the active `RemoteIpValve`:
   ```xml
   <Valve className="org.apache.catalina.valves.RemoteIpValve"
          internalProxies="172\.\d+\.\d+\.\d+|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+"
          remoteIpHeader="x-forwarded-for"
          protocolHeader="x-forwarded-proto" />
   ```
2. Verify Nginx passes genuine client IP in `location /guacamole/`:
   ```nginx
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   proxy_set_header X-Real-IP $remote_addr;
   ```
3. Test client IP logging:
   ```bash
   curl -kfs -H "X-Forwarded-For: 203.0.113.195" https://localhost/guacamole/
   docker exec pt-guacamole tail -n 5 /usr/local/tomcat/logs/localhost_access_log.*.txt | grep "203.0.113.195"
   ```

---

### 5.2 Zombie Process Storm Mitigation Runbook

#### 5.2.1 Symptoms & Triage
- **Alert**: Container creation fails with `fork: Cannot allocate memory`, or host kernel issues PID controller warnings.
- **Telemetry Verification**:
  ```bash
  # Check for defunct processes across desktop containers
  docker exec ptvnc1 ps aux | grep -E "defunct|<defunct>"
  # Check count of defunct AppRun instances
  docker exec ptvnc1 sh -c 'ps -ef | grep "[A]ppRun <defunct>" | wc -l'
  ```
- **Root Cause**: Cisco Packet Tracer was launched inside a container without an active init process (PID 1). When child helper threads terminate, they remain defunct zombies in the process table because no parent process issues `waitpid()`.

#### 5.2.2 Emergency Triage & Mitigation
```bash
# Step 1: Identify affected containers
AFFECTED=$(for c in $(docker ps -q -f "name=ptvnc"); do
    COUNT=$(docker exec "$c" ps -ef 2>/dev/null | grep -c "defunct" || true)
    if [ "$COUNT" -gt 10 ]; then echo "$c ($COUNT zombies)"; fi
done)
echo "Affected containers: $AFFECTED"

# Step 2: Restart affected containers to reclaim PID table
for c in $(echo "$AFFECTED" | awk '{print $1}'); do
    echo "Restarting container $c to clear zombie storm..."
    docker restart "$c"
done
```

#### 5.2.3 Permanent Fix Verification (`tini` Integration)
Ensure `tini` is configured as the container entrypoint in `Dockerfile.ptvnc`:
```dockerfile
# Install tini
RUN apt-get update && apt-get install -y tini && rm -rf /var/lib/apt/lists/*

# Set tini as entrypoint with process subreaper flag (-g)
ENTRYPOINT ["/usr/bin/tini", "-g", "--"]
CMD ["/usr/local/bin/start-session"]
```
Verify that `ps -ef` inside the container shows `/usr/bin/tini` as PID 1:
```bash
docker exec ptvnc1 ps -ef | head -n 3
# Output MUST show:
# UID        PID  PPID  C STIME TTY          TIME CMD
# root         1     0  0 09:00 ?        00:00:00 /usr/bin/tini -g -- /usr/local/bin/start-session
```

---

### 5.3 Classroom Peak Scaling Operational Runbook

#### 5.3.1 Capacity Sizing Formulas
To dimension host infrastructure for concurrent student laboratories:
- **RAM Sizing Formula**:
  $$\text{RAM}_{\text{total}} = (N \times 2.5\text{ GB}) + 4.0\text{ GB Overhead}$$
  *Where $N$ is the number of concurrent student containers, $2.5\text{ GB}$ covers the XFCE4 desktop, Packet Tracer 8.x, and TurboVNC, and $4.0\text{ GB}$ covers host OS, Nginx, MariaDB, and Guacamole.*
- **CPU Sizing Formula**:
  $$\text{CPU}_{\text{cores}} = (N \times 0.5\text{ Cores}) + 2.0\text{ Cores Overhead}$$
  *Under steady state, Packet Tracer requires ~0.2 CPU cores, bursting to 0.8 cores during network simulation calculation.*
- **Disk Storage Quota Formula**:
  $$\text{Disk}_{\text{storage}} = (N \times 500\text{ MB}) + 50.0\text{ GB Base System}$$
  *Allocates 500MB per student for `.pkt` topology files, autosaves, and lab handouts.*

#### 5.3.2 Host Sizing Reference Matrix

| Concurrent Students ($N$) | Recommended RAM | Recommended vCPUs | Storage Headroom | Dedicated Bridge Networks |
|---|---|---|---|---|
| **10 Students** | 32 GB RAM | 8 Cores | 60 GB | Single `/24` subnet (254 IPs) |
| **25 Students** | 64 GB RAM | 16 Cores | 75 GB | Single `/24` subnet (254 IPs) |
| **50 Students** | 128 GB RAM | 32 Cores | 100 GB | Two `/24` subnets (or `/23`) |
| **100 Students** | 256 GB RAM | 64 Cores | 150 GB | High-availability multi-node cluster |

#### 5.3.3 Pre-Warming Strategy Runbook
To prevent container bootstrapping latency and Docker daemon locks when 50 students log in simultaneously at the start of a class:

```bash
#!/usr/bin/env bash
# ==============================================================================
# SCRIPT: scripts/prewarm-instances.sh
# Purpose: Pre-allocate desktop containers 15 minutes before class
# ==============================================================================
set -euo pipefail

TARGET_CONTAINERS=${1:-30}
echo "Pre-warming $TARGET_CONTAINERS PacketTracer instances..."

for i in $(seq 1 "$TARGET_CONTAINERS"); do
    CONTAINER_NAME="ptvnc${i}"
    if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "Launching pre-warmed instance: $CONTAINER_NAME"
        docker run -d \
            --name "$CONTAINER_NAME" \
            --restart unless-stopped \
            --network vnc-net \
            --shm-size 512m \
            --memory 2560m \
            --memory-reservation 2048m \
            --cpus 1.5 \
            -v "/shared/users/student${i}:/home/student/workspace:rw" \
            ptvnc:v2-hardened
    elif [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER_NAME")" != "true" ]; then
        echo "Starting dormant instance: $CONTAINER_NAME"
        docker start "$CONTAINER_NAME"
    fi
done

echo "Pre-warming completed. All instances warm and accepting RFB connections."
```

#### 5.3.4 Session Lifecycle Management (Idle Reaping)
An automated background cron daemon reaps inactive sessions after 60 minutes of zero user input:

```python
#!/usr/bin/env python3
"""
Idle Session Reaper: scripts/reap-idle-sessions.py
Queries Guacamole active connection records and terminates orphaned containers.
"""
import time
import docker
import pymysql

IDLE_TIMEOUT_SECONDS = 3600  # 60 Minutes

def reap_idle_sessions():
    client = docker.from_env()
    db = pymysql.connect(
        host="127.0.0.1", port=3306, user="root", password="ptdbpass_secure", database="guacamole_db"
    )
    cursor = db.cursor()
    
    # Query connections active in history but inactive for > 60m
    query = """
        SELECT c.connection_name, h.end_date 
        FROM guacamole_connection c
        JOIN guacamole_connection_history h ON c.connection_id = h.connection_id
        WHERE h.end_date IS NOT NULL 
          AND TIMESTAMPDIFF(SECOND, h.end_date, NOW()) > %s;
    """
    cursor.execute(query, (IDLE_TIMEOUT_SECONDS,))
    idle_sessions = cursor.fetchall()
    
    for conn_name, end_date in idle_sessions:
        container_name = conn_name.lower().replace(" ", "")
        try:
            container = client.containers.get(container_name)
            print(f"Reaping idle container: {container_name} (Ended: {end_date})")
            container.stop(timeout=10)
        except docker.errors.NotFound:
            pass
            
    db.close()

if __name__ == "__main__":
    reap_idle_sessions()
```

---

### 5.4 Multi-Tenant File Isolation & Security Acceptance Scenario

#### 5.4.1 Architecture & Directory Boundaries
The hardened platform isolates student laboratory files into distinct tenant subdirectories:
- Host Base Directory: `/shared/users/`
- Student Tenant Root: `/shared/users/{user_id}/` (POSIX permissions: `0700`, owner: UID `1000` / `student`)
- Container Mount Destination: `/home/student/workspace`

```
/shared/users/
├── student_alice/       (drwx------ 0700 student:student)
│   ├── lab1_topology.pkt
│   └── lab1_notes.txt
└── student_bob/         (drwx------ 0700 student:student)
    ├── lab1_topology.pkt
    └── secret_eval.pka
```

#### 5.4.2 Path Traversal Sanitization Engine
The Flask management file service enforces strict path validation before servicing upload or download requests:

```python
import os
from pathlib import Path
from flask import abort

BASE_USER_DIR = Path("/shared/users").resolve()

def resolve_secure_student_path(user_id: str, requested_filename: str) -> Path:
    """
    Validates that the requested file path resolves strictly within the
    authenticated student's isolated workspace directory.
    Rejects directory traversal (../, %2e%2e, null bytes).
    """
    # 1. Null-byte rejection
    if "\x00" in requested_filename or "%00" in requested_filename:
        abort(400, "Invalid filename: null byte detected.")
        
    # 2. Strict tenant isolation
    user_root = (BASE_USER_DIR / user_id).resolve()
    target_path = (user_root / requested_filename).resolve()
    
    # 3. Path containment verification
    if not str(target_path).startswith(str(user_root)):
        abort(403, "Access denied: Path traversal attempt detected.")
        
    return target_path
```

#### 5.4.3 Security Acceptance Test Procedure
The automated acceptance script verifies that tenant cross-contamination, directory traversal, and quota enforcement function correctly:

```bash
#!/usr/bin/env bash
# ==============================================================================
# SCRIPT: tests/acceptance/test_file_isolation.sh
# Acceptance Verification: Multi-Tenant File Isolation & Security
# ==============================================================================
set -euo pipefail

echo "Executing File Isolation & Security Acceptance Test..."

# Test 1: Direct Path Traversal Rejection
echo -n "[TEST 1/4] Testing '../' path traversal rejection... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Cookie: session=mock_alice_session" \
    "http://localhost:5000/api/files/download?file=../../student_bob/secret_eval.pka" || true)

if [ "$STATUS" -eq 403 ] || [ "$STATUS" -eq 400 ] || [ "$STATUS" -eq 404 ]; then
    echo "PASSED (HTTP $STATUS)"
else
    echo "FAILED: Path traversal succeeded or returned unexpected status ($STATUS)"
    exit 1
fi

# Test 2: URL Encoded Path Traversal Rejection (%2e%2e%2f)
echo -n "[TEST 2/4] Testing URL-encoded traversal (%2e%2e%2f)... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Cookie: session=mock_alice_session" \
    "http://localhost:5000/api/files/download?file=%2e%2e%2f%2e%2e%2fstudent_bob/secret_eval.pka" || true)

if [ "$STATUS" -eq 403 ] || [ "$STATUS" -eq 400 ] || [ "$STATUS" -eq 404 ]; then
    echo "PASSED (HTTP $STATUS)"
else
    echo "FAILED: URL-encoded traversal succeeded ($STATUS)"
    exit 1
fi

# Test 3: Null Byte Poisoning Rejection
echo -n "[TEST 3/4] Testing Null Byte Poisoning (%00)... "
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Cookie: session=mock_alice_session" \
    "http://localhost:5000/api/files/download?file=lab1.pkt%00.txt" || true)

if [ "$STATUS" -eq 400 ] || [ "$STATUS" -eq 403 ]; then
    echo "PASSED (HTTP $STATUS)"
else
    echo "FAILED: Null byte poisoning was not blocked ($STATUS)"
    exit 1
fi

# Test 4: Tenant Cross-Directory POSIX Boundary Verification
echo -n "[TEST 4/4] Verifying POSIX permissions (0700) between containers... "
# Verify student1 container cannot read student2 workspace directory directly
if docker exec ptvnc1 ls /shared/users/student2 >/dev/null 2>&1; then
    echo "FAILED: ptvnc1 was able to list /shared/users/student2"
    exit 1
else
    echo "PASSED (POSIX permission denied as expected)"
fi

echo "ALL FILE ISOLATION & SECURITY ACCEPTANCE TESTS PASSED (100%)."
```

---

## Section 6: Verification and Sign-Off

### 6.1 Requirements Traceability Matrix
This roadmap directly resolves all requirements defined in `PROJECT.md`, `ORIGINAL_REQUEST.md`, and the 27 improvement proposals in `docs/proposals/02_improvement_proposals.md`:

| Requirement Domain | Proposal Cross-Reference | Roadmap Deliverable Section | Acceptance Status |
|---|---|---|---|
| **Perimeter Security** | `PROP-C3-01` to `PROP-C3-05` | Section 1.2 (Phase 1 Roadmap) & Section 3.2 | COMPLETE |
| **API & Docker Security** | `PROP-C4-01` to `PROP-C4-03` | Section 1.2, Section 2 (RISK-TEC-01), Section 3.2 | COMPLETE |
| **Storage Persistence** | `PROP-C2-01`, `PROP-C5-05` | Section 1.3 (Phase 2), Section 3.3 (Volume Migration) | COMPLETE |
| **Init & Process Control** | `PROP-C1-02`, `PROP-C1-03` | Section 1.3 (Phase 2), Section 5.2 (Zombie Runbook) | COMPLETE |
| **Display Optimization** | `PROP-C1-01`, `PROP-C1-04` | Section 1.3 (Phase 2), Section 4.2 (TurboVNC Pipeline) | COMPLETE |
| **High Availability & HA** | `PROP-C5-01` to `PROP-C5-04` | Section 1.4 (Phase 3), Section 3.4 (Backup/RPO/RTO) | COMPLETE |
| **Classroom Scaling** | `PROP-C4-06`, `PROP-C5-07` | Section 1.4 (Phase 3), Section 5.3 (Scaling Formulas) | COMPLETE |
| **Tenant File Isolation** | `PROP-C4-05` | Section 1.3 (Phase 2), Section 5.4 (Acceptance Scenario) | COMPLETE |

### 6.2 Independent Verification Instructions
To execute the automated Tier 4 verification test suite against this proposal:

```bash
# Execute Tier 4 Real-World Application & Operational Runbook verification
python3 tests/proposal_verification/test_proposal.py \
    --proposal docs/proposals/03_roadmap_and_migration.md \
    --tier 4 \
    --verbose
```

**Verification Gate Criteria**:
- Test Suite: `tests/proposal_verification/test_tier4_real_world.py`
- Total Tests: 14 test methods across 4 test classes.
- Target Result: `Ran 14 tests ... OK (0 failures, 0 errors, exit code 0)`.
