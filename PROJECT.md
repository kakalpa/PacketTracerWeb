# Project: PacketTracerWeb Production Readiness, Operational Stability & Hardening Proposal

## Architecture
PacketTracerWeb provides browser-based, multi-user virtualized Cisco Packet Tracer instances via an HTML5 web portal.
The system comprises five core architectural components:
1. **Virtualized Desktop Container (`ptvnc`)**: Ubuntu 22.04 base, TurboVNC / VirtualGL, XFCE4 desktop, proprietary Cisco Packet Tracer AppImage/deb installation, running with display virtualization.
2. **Apache Guacamole Stack (`guacd`, `pt-guacamole`, `guacamole-mariadb`)**: Clientless remote desktop gateway translating VNC RFB protocol into Guacamole protocol over WebSockets, with MariaDB user authentication and connection mapping.
3. **Nginx Edge Gateway (`pt-nginx`)**: Custom compiled reverse proxy terminating TLS 1.2/1.3, handling GeoIP filtering, rate limiting, and routing traffic to Guacamole (`/guacamole/`, `/`) and Flask management (`:5000`).
4. **Flask/Gunicorn Management Service (`pt-management`)**: Python 3.11 web service interfacing with Docker daemon and MariaDB to manage student user provisioning, container lifecycle, `.env` configuration, and file sharing.
5. **Deployment & Orchestration Harness**: Procedural shell scripts (`deploy.sh`, `deploy-full.sh`, `add-instance.sh`, `remove-instance.sh`, `health_check.sh`) and Docker Compose definitions managing service bootstrapping, networking, and verification.

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
         │       │                                             (Persistent volume, connection params)
         │       ▼ (Port 4822)
         │    [ Guacamole Proxy Daemon (guacd) ]
         │       │
         │       ▼ (RFB Port 5901, isolated network)
         │    [ Virtualized PT Containers (ptvnc1..N) ]
         │       ├── TurboVNC + XFCE4 + Cisco Packet Tracer
         │       └── Tini Init, /dev/shm 512MB, 2GB RAM
         │
         └──► :5000 (Management Portal)
                 │
                 ▼
              [ Flask / Gunicorn App (pt-management) ]
                 ├── Authenticated REST API & CSRF Protection
                 ├── Isolated Per-User File Storage (/shared/users/{user})
                 └── Docker Socket Proxy (Restricted container-only API)
```

## Feature Inventory
| # | Feature / Assessment Area | Description | Milestone | Source |
|---|---------------------------|-------------|-----------|--------|
| 1 | C1: VNC & Display Server Audit | Eliminate dual Xvfb/Xvnc conflict, fix `start-session`, enforce VNC auth | M1, M2 | Survey 1 |
| 2 | C1: Process Supervision & Init | Implement `tini`/supervisor, eliminate defunct `[AppRun]` zombie leaks | M1, M2 | Survey 1, 3 |
| 3 | C1: PT Container Resource Tuning | Set `/dev/shm=512m`, `nofile=65536`, `nproc=4096`, 2.5GB RAM, VirtualGL/GPU | M1, M2 | Survey 1, 3 |
| 4 | C1: Installer & Volume Mutex | Fix `pt-install.sh` `.AppImage` detection, lock `pt_opt` shared volume | M1, M2 | Survey 1 |
| 5 | C1: Clipboard & Audio Subsystem | Fix `autocutsel` integration in TurboVNC, evaluate PulseAudio streaming | M1, M2 | Survey 1 |
| 6 | C2: MariaDB Volume Persistence | Replace anonymous Docker volume with named `mariadb_data` volume | M1, M2 | Survey 1, 3 |
| 7 | C2: Guacamole Connection Deduplication | Fix `NULL` parent_id duplicate connections bug in `generate-dynamic-connections.sh` | M1, M2 | Survey 1 |
| 8 | C2: Tomcat RemoteIpValve & Bans | Add `RemoteIpValve` to `server.xml` to prevent Nginx proxy IP ban lockouts | M1, M2 | Survey 1 |
| 9 | C2: Guacamole Proxy Buffering | Add `proxy_buffering off;` and WebSocket map in Nginx configuration | M1, M2 | Survey 1, 2 |
| 10 | C2: Non-Destructive Deprovisioning | Refactor `remove-instance.sh` to remove single container without restarting stack | M1, M2 | Survey 1, 3 |
| 11 | C3: Modern GeoIP2 Migration | Replace deprecated GeoIP1 with `ngx_http_geoip2_module` & official MMDB | M1, M2 | Survey 2, 3 |
| 12 | C3: GeoIP Filtering Bug Fixes | Fix ISO country codes (`UK`->`GB`, `SL`->`LK`), fix regex bypass vulnerabilities | M1, M2 | Survey 2 |
| 13 | C3: SSL/TLS Hardening & Ciphers | Enforce Mozilla Intermediate ciphers, HSTS, OCSP stapling, SSL session caching | M1, M2 | Survey 2 |
| 14 | C3: HTTP Security Headers | Add CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy, server_tokens off | M1, M2 | Survey 2 |
| 15 | C3: Perimeter & Port 5000 Hardening | Apply rate limiting & security headers to management port 5000, remove `/downloads/` autoindex | M1, M2 | Survey 2, 3 |
| 16 | C4: Docker Socket Proxy Security | Replace direct `/var/run/docker.sock` mount with restricted `docker-socket-proxy`, non-root user | M1, M2 | Survey 2, 3 |
| 17 | C4: API Authentication & CSRF | Remove unauthenticated `/api/containers` & IP bypasses; enforce session auth & CSRF | M1, M2 | Survey 2, 3 |
| 18 | C4: Secret & Credential Hardening | Enforce mandatory `SECRET_KEY`, dynamic password generation, eliminate default `IlovePT` | M1, M2 | Survey 2, 3 |
| 19 | C4: Container Provisioning Unification | Standardize on Docker SDK, unify network attachment (`ptnet`), eliminate dev machine paths | M1, M2 | Survey 2, 3 |
| 20 | C4: Database Pooling & Bug Fixes | Fix fatal SQL bug in `delete_connection`, unify `DB_PASSWORD`, add connection pooling | M1, M2 | Survey 1, 2 |
| 21 | C4: Isolated File Management | Transition from world-writable `/shared` to per-user isolated directories & secure download APIs | M1, M2 | Survey 1, 2 |
| 22 | C4: Gunicorn Concurrency & Async | Switch to async worker model and background job queues for provisioning operations | M1, M2 | Survey 2 |
| 23 | C5: Health Checks & Startup Sequencing | Implement Docker `HEALTHCHECK` across all containers; replace 115s sleep delays with health probes | M1, M2 | Survey 3 |
| 24 | C5: Network Topology & Segmentation | Segment network into `frontend-net`, `backend-net`, `vnc-net`; eliminate deprecated `--link` | M1, M2 | Survey 3 |
| 25 | C5: Container Privilege & Capability Dropping | Apply `--cap-drop=ALL`, `--security-opt=no-new-privileges`, read-only root filesystems | M1, M2 | Survey 3 |
| 26 | C5: Logging, Log Rotation & Metrics | Configure Docker json-file log rotation, Nginx log rotation, audit logging, Prometheus metrics | M1, M2 | Survey 3 |
| 27 | C5: Backup & Disaster Recovery | Create automated database backup/restore scripts with rotation; fix destructive `cleanup-all.sh` | M1, M2 | Survey 3 |
| 28 | C5: Dependency & Image Tag Pinning | Pin upstream container image tags (`mariadb`, `guacd`, `guacamole`), verify binary checksums | M1, M2 | Survey 3 |
| 29 | Operational Domain Categorization | Structure all proposals across Security, Performance, HA/Reliability, Usability, Maintainability | M2 | Survey 1, 2, 3 |
| 30 | Production Hardening Roadmap | 3-Phase phased rollout (Immediate Hotfixes, Structural Hardening, Enterprise Scaling) | M3 | Survey 1, 2, 3 |
| 31 | Risk Assessment & Migration Engineering | Pre-migration checklists, failure modes, rollback procedures, validation scripts | M3 | Survey 1, 2, 3 |
| 32 | Master Markdown Deliverable | Compile, format, and publish comprehensive `PRODUCTION_HARDENING_PROPOSAL.md` in repository | M4 | Survey 1, 2, 3 |
| 33 | E2E Proposal Verification Test Suite | Implement and pass 100% opaque-box verification test suite for proposal requirements | M5 (Final) | All |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | System Assessment & Component Audit | Comprehensive technical audit of 5 components across 5 operational domains (`docs/proposals/01_system_assessment.md`) | none | DONE |
| M2 | Categorized Improvement Proposals | Structured proposals for all identified issues with technical solutions and impact analysis (`docs/proposals/02_improvement_proposals.md`) | M1 | DONE |
| M3 | Production Roadmap & Migration Plan | Implementation feasibility, risk matrix, phased rollout roadmap, migration & rollback procedures (`docs/proposals/03_roadmap_and_migration.md`) | M2 | IN_PROGRESS |
| M4 | Master Deliverable Assembly | Publication of `PRODUCTION_HARDENING_PROPOSAL.md` integrating executive summary, audit, proposals, and roadmap | M3 | PLANNED |
| M5 | Final Verification & Adversarial Hardening | E2E requirement test suite pass (Tiers 1-4) & adversarial review (Tier 5) | M4, E2E Track | PLANNED |

## Interface Contracts

### M1 (Assessment) ↔ M2 (Proposals)
- **Format**: Structured Markdown document `docs/proposals/01_system_assessment.md`.
- **Contract Schema**:
  - Each finding must have a unique identifier: `[FINDING-C<component_num>-<domain_code>-<item_num>]` (e.g., `FINDING-C1-SEC-01`, `FINDING-C3-PERF-02`).
  - Required sections per finding: Target File, Exact Code Reference / Line Numbers, Limitation / Vulnerability Description, Empirical Evidence / Reproduction Command, Current Impact.
  - Operational Domains: `SEC` (Security & Hardening), `PERF` (Performance & Scaling), `REL` (High Availability & Reliability), `USE` (Usability), `MAINT` (Maintainability).

### M2 (Proposals) ↔ M3 (Roadmap & Migration)
- **Format**: Structured Markdown document `docs/proposals/02_improvement_proposals.md`.
- **Contract Schema**:
  - Each proposal maps directly to one or more finding IDs: `[PROP-C<component_num>-<num>]`.
  - Required fields per proposal:
    - Current State & Risk
    - Proposed Solution & Technical Architecture
    - Impact on Production Stability
    - Implementation Complexity (Low / Medium / High)
    - Affected Components & Files

### M3 (Roadmap) ↔ M4 (Master Deliverable Assembly)
- **Format**: Structured Markdown document `docs/proposals/03_roadmap_and_migration.md`.
- **Contract Schema**:
  - Phased Rollout Matrix (Phase 1: Zero-Downtime Hotfixes & Security Patches; Phase 2: Architectural Decoupling & Container Hardening; Phase 3: High Availability, Observability & Enterprise Scaling).
  - Risk Mitigation & Rollback Protocol per phase.
  - Verification & Acceptance Testing procedures.

### M4 (Assembly) ↔ M5 (Final E2E Verification)
- **Primary Deliverable**: `/home/kalpa/Projects/TUAS/PacketTracerWeb/PRODUCTION_HARDENING_PROPOSAL.md`.
- **Validation Contract**: Must satisfy 100% of acceptance criteria in `ORIGINAL_REQUEST.md` and pass all test tiers in `tests/proposal_verification/test_proposal.py`.

## Code Layout
```
/home/kalpa/Projects/TUAS/PacketTracerWeb/
├── PRODUCTION_HARDENING_PROPOSAL.md       # Master deliverable document
├── PROJECT.md                             # Orchestration index and project scope
├── docs/
│   └── proposals/
│       ├── 01_system_assessment.md        # M1 deliverable
│       ├── 02_improvement_proposals.md    # M2 deliverable
│       └── 03_roadmap_and_migration.md    # M3 deliverable
├── tests/
│   └── proposal_verification/
│       ├── test_proposal.py               # E2E test suite runner
│       ├── test_tier1_feature_coverage.py
│       ├── test_tier2_boundary_corner.py
│       ├── test_tier3_cross_feature.py
│       └── test_tier4_real_world.py
└── .agents/teamwork/                      # Agent orchestration metadata
```
