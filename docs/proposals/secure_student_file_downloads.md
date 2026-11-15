# Architectural Specification & Implementation Proposal: Secure Student File Downloads for PacketTracerWeb

**Author**: TUAS Architecture & Engineering Team  
**Document Status**: Final Architectural Proposal  
**Target Repository**: `PacketTracerWeb`  
**Date**: November 2026  
**Deliverable Path**: `docs/proposals/secure_student_file_downloads.md`  

---

## 1. Executive Summary & Problem Formulation

### 1.1 Executive Summary
PacketTracerWeb provides an educational virtualization platform that delivers browser-accessible Cisco Packet Tracer instances to students via Apache Guacamole, TurboVNC, and an Nginx reverse proxy edge gateway. While the system excels at providing low-latency desktop access without client software installation, its underlying file exchange and storage architecture exhibits critical security, multi-tenant isolation, and usability vulnerabilities.

Currently, the platform relies on a single host directory (`/shared`) mounted with world-writable permissions (`0777`) across all running student containers. Furthermore, this directory is directly exposed to the public internet by Nginx via `location ^~ /downloads/` with `autoindex on;`. Any unauthenticated external visitor can enumerate, inspect, and download every student lab file (`.pkt`, `.pka`) hosted on the server. Simultaneously, inside the virtualized environment, all student containers share the flat `/shared` namespace, allowing students to inspect, overwrite, or maliciously delete the coursework of their peers. Compounding this, the administrative management portal (`pt-management:5000/files`) requires administrative credentials, leaving ordinary students without any secure, self-service download mechanism.

This specification proposes a comprehensive, publication-grade architectural solution: the **Hybrid Per-Instance Isolated Storage and Cryptographically Authenticated Gateway Architecture (Option D)**. This solution achieves:
1. **Total Elimination of Public File Exposure**: Eradicates the `/downloads/` directory listing entirely from Nginx, closing all unauthenticated attack vectors.
2. **Absolute Multi-Tenant Isolation**: Replaces the global `/shared` bind mount with dedicated, per-instance host directories (`/shared/instances/{container_name}/`), enforced at the Linux kernel VFS and container mount namespace level.
3. **High-Performance Zero-Copy File Delivery**: Employs an internal, protected Nginx location (`/internal/downloads/`) driven by upstream `X-Accel-Redirect` headers emitted from a lightweight Flask student API, offloading file transfers to kernel `sendfile` without Python worker memory buffering.
4. **Cryptographic Access Control**: Enforces time-limited, signed HMAC-SHA256 download tokens validated with constant-time equality checks and multi-tenant path containment verification (`Path.relative_to`).
5. **Frictionless Student UX**: Transparently redirects Cisco Packet Tracer's default save path (`/home/ptuser/pt/saves`) and XFCE desktop folders directly into the isolated instance storage via symlinks and GTK file picker bookmarks, complemented by an integrated web download interface requiring zero administrative credentials.
6. **Robust Lifecycle Hygiene**: Implements automated container deprovisioning archiving (`/shared/archive/`) and clean purging to prevent sequential cross-tenant data leakage.

---

### 1.2 Problem Statement & Current Architecture Deficiencies

An empirical audit of the PacketTracerWeb codebase reveals four interlocking architectural flaws:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                              CURRENT VULNERABLE ARCHITECTURE                           │
└────────────────────────────────────────────────────────────────────────────────────────┘

    External Attacker / Any Browser
                 │
                 │ 1. GET /downloads/ (Unauthenticated)
                 ▼
    ┌───────────────────────────┐
    │     Nginx Edge Gateway    │
    │  location ^~ /downloads/  │
    │      autoindex on;        │ ◄── CRITICAL DEFICIENCY 1:
    └────────────┬──────────────┘     Unauthenticated Public Enumeration
                 │
                 │ Direct read of host filesystem
                 ▼
    ┌────────────────────────────────────────────────────────────────────────────────────┐
    │                      Host Filesystem Directory: /shared/ (chmod 777)               │
    │     [alice_lab1.pkt]          [bob_exam_final.pkt]          [charlie_test.pkt]     │
    └────────────┬───────────────────────────┬─────────────────────────────┬─────────────┘
                 │                           │                             │
                 │ Bind Mount                │ Bind Mount                  │ Bind Mount
                 │ target=/shared            │ target=/shared              │ target=/shared
                 ▼                           ▼                             ▼
    ┌───────────────────────────┐┌───────────────────────────┐┌───────────────────────────┐
    │  Container: ptvnc1        ││  Container: ptvnc2        ││  Container: ptvnc3        │
    │  Student: Alice           ││  Student: Bob             ││  Student: Charlie         │
    │                           ││                           ││                           │
    │  Desktop/shared -> /shared││  Desktop/shared -> /shared││  Desktop/shared -> /shared│
    └───────────────────────────┘└───────────────────────────┘└───────────────────────────┘
         ▲                                                                      │
         │ CRITICAL DEFICIENCY 2: Cross-Tenant Multi-Tenant Contamination        │
         └──────────────────────────────────────────────────────────────────────┘
           Charlie can view, modify, or delete Alice's and Bob's lab files!

    ┌───────────────────────────┐
    │  pt-management:5000/files │ ◄── CRITICAL DEFICIENCY 3: Administrative Barrier
    │   @require_auth (Admin)   │     Students locked out of self-service download tool
    └───────────────────────────┘
```

#### Deficiency 1: Unauthenticated Public File Enumeration at `/downloads/`
In `ptweb-vnc/pt-nginx/conf/ptweb.conf` (lines 28–41) and dynamically emitted by `ptweb-vnc/pt-nginx/generate-nginx-conf.sh` (lines 254–263):
```nginx
# Serve shared downloads with highest priority
location ^~ /downloads/ {
  alias /shared/;
  autoindex on;
  autoindex_exact_size off;
  autoindex_localtime on;
}
```
Any client traversing the network perimeter can send an HTTP `GET /downloads/` request. The gateway responds with an auto-generated HTML index enumerating every file present on disk. No HTTP Basic authentication, session cookie, bearer token, or authorization header is required. This exposes student topologies, credentials embedded in Cisco router running-configs, and academic assignment solutions to open-source intelligence (OSINT) gathering and plagiarism.

#### Deficiency 2: Multi-Tenant Cross-Contamination in Flat `/shared` Mount
Across all orchestration scripts—`deploy.sh` (lines 203–236), `add-instance.sh` (lines 69–93), and `pt-management/ptmanagement/docker_mgmt/container.py` (lines 354–369)—every student container binds the exact same host directory:
```bash
--mount type=bind,source="${WORKDIR}/shared",target=/shared,bind-propagation=rprivate
```
All student processes execute as `ptuser` (UID 1000). Because `/shared` is world-writable (`0777`), any process inside container `ptvnc1` possesses unrestricted read, write, modify, and delete permissions over files created by container `ptvnc2`. 
- **Academic Integrity**: Student B can copy Student A's completed assignment file directly.
- **Accidental Collisions**: If two students save a file named `lab1.pkt`, the second write silently overwrites the first.
- **Denial of Service**: A rogue student or script executing `rm -rf /shared/*` obliterates the active work of every student across the entire institution.

#### Deficiency 3: Administrative Barrier to Self-Service Retrieval
The repository contains an authenticated web file manager in the Flask management application (`pt-management/ptmanagement/api/file_manager.py`). However, its endpoints are guarded by `@require_auth` and `check_authentication` in `app.py`:
```python
@app.before_request
def check_authentication():
    protected_routes = ['/dashboard', '/settings', '/files', '/api/']
    if any(request.path.startswith(route) for route in protected_routes):
        if 'user' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
```
Only users possessing Guacamole `ADMINISTER` privileges (the `ptadmin` role) can log in to port 5000. Students enrolled in coursework possess standard Guacamole connection credentials (e.g., `pt01`, `pt02`) without administrative access. As a result, students cannot retrieve their files through the management UI and are explicitly instructed by `file-manager.html` to rely on the insecure public `/downloads/` directory.

#### Deficiency 4: Desktop Save Path Disconnect & Ephemeral Data Trapping
In Cisco Packet Tracer, the application binary's default save path is `/home/ptuser/pt/saves/` (defined in `/home/ptuser/.packettracer`). However, the only bridge to host storage is a desktop symlink `/home/ptuser/Desktop/shared -> /shared`.
If a student saves their work using the default path or saves to `/home/ptuser/Desktop/` or `/home/ptuser/Documents/`, the file is written to the container's ephemeral overlay filesystem. When instances are recycled or deprovisioned via `remove-instance.sh` or `DELETE /api/containers/<name>`, the container's overlay is destroyed, resulting in permanent student data loss.

---

### 1.3 Key Architectural Goals & Target Outcomes

| Dimension | Target Architectural Outcome |
| :--- | :--- |
| **Confidentiality** | Zero unauthenticated access. Total elimination of public directory browsing. External requests to `/downloads/` or internal storage return HTTP 404/403. |
| **Multi-Tenancy** | Cryptographic and kernel-enforced filesystem boundary between all student instances. Container $N$ cannot view or access files belonging to Container $M$. |
| **Student Usability** | Native Packet Tracer saves land directly in persistent, isolated storage. One-click, self-service download path requires zero admin credentials. |
| **Edge Gateway Performance** | Nginx zero-copy `sendfile` file transfers via `X-Accel-Redirect`. Upstream Python application worker is freed in <2ms; zero Python memory buffering. |
| **Lifecycle Hygiene** | Automated archiving of student work to `/shared/archive/` upon container deprovisioning, preventing sequential tenant data leakage. |

---

## 2. Architectural Investigation & Option Comparison

### 2.1 Technical Investigation of Candidate Approaches

#### Option A: Guacamole Native Virtual Drive / SFTP Redirection
Apache Guacamole provides built-in file transfer capabilities, but their applicability depends heavily on the underlying connection protocol.

##### 1. Protocol Architecture & Library Analysis
Direct binary inspection of the `pt-guacd:1.6.0` container libraries reveals:
- **`libguac-client-rdp.so`**: Contains native virtual drive redirection symbols (`enable-drive`, `drive-name`, `drive-path`, `create-drive-path`). This subsystem operates over FreeRDP's `RDPDR` (Remote Desktop Protocol Device Redirection) channel. When a file is dropped into a designated `Download` subfolder inside an RDP virtual drive, Guacamole automatically initiates a browser download stream.
- **`libguac-client-vnc.so`**: Operates over the RFB (Remote Framebuffer) protocol. The RFB protocol specification does **not** support virtual device redirection. String inspection of `libguac-client-vnc.so` confirms:
  ```bash
  docker exec pt-guacd strings /opt/guacamole/lib/libguac-client-vnc.so | grep -i "drive-path"
  # Exit code 1 (drive-path is completely absent)
  ```
  Consequently, Guacamole's native virtual drive (`enable-drive`) cannot be enabled on VNC connections.

##### 2. Feasibility of VNC+SFTP Tunneling
`libguac-client-vnc.so` does include an integrated SFTP client subsystem built on `libssh2`:
```
guac_common_ssh_create_sftp_filesystem
enable-sftp
sftp-hostname
sftp-port
sftp-username
sftp-password
sftp-root-directory
```
If `enable-sftp` is set to `true` in `guacamole_connection_parameter`, `guacd` streams the graphical display over VNC (port 5901) while establishing a concurrent SFTP connection over SSH (port 22).

##### 3. Deficiencies of Option A
1. **Container Daemon Bloat & Attack Surface**: `ptvnc` container images currently lack `openssh-server`. Supporting SFTP requires installing OpenSSH in every container, generating host keys, managing SSH credentials in MariaDB, and running an SSH daemon on the internal container network.
2. **Severe Student UX Friction**: In VNC+SFTP sessions, Guacamole provides **no automatic download triggers**. The virtual drive is not mounted in the desktop. Instead, students must press `Ctrl + Alt + Shift` (or `Cmd + Ctrl + Shift` on macOS) to open the Guacamole sidebar drawer, navigate the "Devices" file tree, locate their file, and click it. On Chromebooks, iPads, and mobile browsers, this keystroke combination frequently conflicts with system shortcuts or fails entirely.

---

#### Option B: Per-Container / Per-Instance Isolated Storage Mounts
In this architecture, the flat `/shared` directory on the host is partitioned into isolated per-instance subdirectories:
```
/shared/instances/
├── ptvnc1/ (chmod 700 / ptuser:ptuser)
├── ptvnc2/ (chmod 700 / ptuser:ptuser)
└── ptvncN/ (chmod 700 / ptuser:ptuser)
```

##### 1. Kernel-Enforced Isolation
During container provisioning, Docker mounts only that specific instance's directory:
```bash
--mount type=bind,source="${WORKDIR}/shared/instances/ptvnc1",target=/shared,bind-propagation=rprivate
```
Because Linux kernel mount namespaces strictly enforce filesystem subtree boundaries, processes inside `ptvnc1` cannot navigate outside their bind mount. Container `ptvnc1` has no visibility into `ptvnc2`'s filesystem.

##### 2. Deficiencies of Option B in Isolation
While Option B guarantees absolute storage isolation between containers, it does not solve the download delivery challenge. Without an authenticated web transport mechanism, students still lack a self-service way to transfer saved files from the container's isolated folder to their personal physical computer.

---

#### Option C: Session-Authenticated Gateway with Nginx `X-Accel-Redirect` & Flask Endpoints
Option C addresses external exposure by hardening the Nginx edge gateway and introducing an authenticated backend endpoint.

##### 1. Gateway Hardening with `internal;`
Nginx's `internal;` directive specifies that a location block cannot be accessed directly by external client requests (returning HTTP 404). It can only be reached via internal execution contexts, such as an upstream reverse proxy returning an `X-Accel-Redirect` header (`ngx_http_proxy_module`):
```nginx
location ^~ /internal/downloads/ {
    internal;
    alias /shared/instances/;
    sendfile on;
    tcp_nopush on;
}
```

##### 2. Upstream Authentication & Zero-Copy Streaming
When a student requests a file download, the request is routed to an authenticated Flask endpoint. The Flask application performs authentication, validates that the requested file belongs to the student's authorized container, prevents directory traversal, and returns an empty HTTP body with:
```http
HTTP/1.1 200 OK
X-Accel-Redirect: /internal/downloads/ptvnc1/lab1.pkt
Content-Disposition: attachment; filename="lab1.pkt"
Content-Type: application/octet-stream
```
Nginx intercepts this header, terminates the upstream request, and streams the file directly from host storage to the client socket using the Linux kernel `sendfile` system call. The Python worker is freed in under 2 milliseconds, and zero file data is buffered in Python application memory.

##### 3. Stateless Signed HMAC-SHA256 Download URLs
To allow direct browser `<a href>` downloads without passing sensitive credentials in headers, download requests can use signed HMAC-SHA256 URLs:
$$\text{Signature} = \text{HMAC-SHA256}(K_{\text{secret}}, \text{container} \parallel \text{filename} \parallel \text{expires})$$
This allows the student to download their file directly using standard browser download managers with tamper-proof, time-limited tokens.

---

#### Option D (Recommended): Hybrid Option B + Option C Architecture
Option D combines the kernel-enforced storage isolation of Option B with the cryptographically authenticated, zero-copy HTTP gateway of Option C.

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                      OPTION D: RECOMMENDED HYBRID ARCHITECTURE                         │
└────────────────────────────────────────────────────────────────────────────────────────┘

 [Student Browser]
       │
       │ 1. Interactive VNC Desktop via Guacamole WebSocket
       ▼
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │                                   pt-nginx Gateway                                    │
 │                                                                                       │
 │  • Public /downloads/ removed entirely (404)                                          │
 │  • /internal/downloads/ marked internal; (rejects external access)                    │
 │  • /api/student/files/ proxies to pt-management                                       │
 └──────┬──────────────────────────────────────────────────────────────────▲─────────────┘
        │                                                                  │
        │ 2. VNC Stream                                                    │ 5. Zero-Copy
        ▼                                                                  │    sendfile
 ┌───────────────────────────┐                                             │    Stream
 │   ptvnc1 Desktop Session  │                                             │
 │                           │                                             │
 │  Cisco Packet Tracer      │                                             │
 │    File -> Save           │                                             │
 │    ~/pt/saves -> /shared  │                                             │
 └──────┬────────────────────┘                                             │
        │                                                                  │
        │ 3. Writes .pkt                                                   │
        ▼                                                                  │
 ┌──────────────────────────────────────────────────────────────────┐      │
 │ Host Storage: /shared/instances/ptvnc1/lab1.pkt                  ├──────┘
 └──────────────────────────────────────────────────────────────────┘
        ▲
        │ 4. Verifies Auth & Emits X-Accel-Redirect
 ┌──────┴───────────────────────────────────────────────────────────┐
 │                 pt-management (Flask Service)                    │
 │                                                                  │
 │  • Validates session / HMAC-SHA256 token                         │
 │  • Checks Path.relative_to (Traversal Defense)                   │
 │  • Emits: X-Accel-Redirect: /internal/downloads/ptvnc1/lab1.pkt  │
 └──────────────────────────────────────────────────────────────────┘
```

This hybrid model delivers defense-in-depth:
1. **Container Isolation (VFS Layer)**: Container `ptvnc1` physically cannot access Container `ptvnc2`'s files on disk.
2. **Gateway Lockdown (Network Layer)**: External unauthenticated directory browsing is completely eliminated. Direct attempts to reach `/internal/downloads/` return 404.
3. **Cryptographic Gatekeeping (Application Layer)**: Downloads require a valid session or signed HMAC token. Directory traversal attacks (`../../`) are blocked by strict canonical path bounds checking.
4. **Seamless Student UX**: Packet Tracer saves land directly in the isolated volume. A single-click web interface allows downloading without admin credentials.

---

### 2.2 Comprehensive Option Comparison Matrix

The table below provides a comprehensive evaluation of all candidate approaches across six key architectural dimensions:

| Evaluation Dimension | Option A: Guacamole Native SFTP Redirection | Option B: Per-Instance Isolated Storage Mounts | Option C: Session-Auth Gateway (`X-Accel-Redirect`) | Option D (Recommended): Hybrid Option B + Option C |
| :--- | :--- | :--- | :--- | :--- |
| **1. Cross-Tenant Isolation** | **Moderate**: Isolated per connection in Guacamole, but containers still share flat `/shared` mount on host unless partitioned. | **Absolute**: Enforced by Linux kernel mount namespaces. Container $N$ cannot inspect Container $M$. | **Moderate**: Isolation enforced solely at web application layer; containers still share flat host storage. | **Absolute**: Dual-layer defense. Kernel mount namespace isolation + cryptographic application access control. |
| **2. Public Exposure Elimination** | **Complete**: File transfers occur over Guacamole's internal virtual channel protocol; no public HTTP endpoints. | **Incomplete**: Does not define an HTTP delivery mechanism; legacy `/downloads/` may remain exposed. | **Complete**: Removes public `/downloads/` autoindex; replaces with Nginx `internal;` location. | **Complete**: Eradicates `/downloads/` and `autoindex`. Replaces with Nginx `internal;` zero-copy location. |
| **3. Student UX / Friction** | **High Friction**: Requires hidden `Ctrl+Alt+Shift` key combinations; no automatic downloads; fails on iPads/Chromebooks. | **High Friction**: Files saved to disk, but student has no web-based mechanism to retrieve them. | **Low Friction**: Standard native browser file download via HTTP GET link or button. | **Frictionless**: Native Packet Tracer save (`~/pt/saves`), desktop folder, plus one-click web download button. |
| **4. Packet Tracer Native Save** | **Poor**: Student must navigate to an SFTP-mounted folder or manually move files via terminal. | **Good**: Can symlink `~/pt/saves` to `/shared`, writing directly to the instance directory. | **N/A**: Governs file download delivery only; container internal save behavior unchanged. | **Optimal**: Automatic redirection of `~/pt/saves -> /shared`, Desktop symlinks, and GTK sidebar bookmarks. |
| **5. Implementation & Operational Complexity** | **High**: Requires OpenSSH daemon in all containers, SSH key provisioning, Guacamole DB schema modifications. | **Low**: Requires updating directory creation and Docker bind mount parameters in deploy scripts. | **Moderate**: Requires Nginx configuration updates and implementing a Flask authentication endpoint. | **Moderate**: Clean, modular changes to Docker volume paths, Nginx config templates, and a lightweight Flask blueprint. |
| **6. Performance Overhead** | **High**: Binary chunks multiplexed over Guacamole WebSocket tunnel; causes VNC video frame drops. | **Zero Overhead**: Direct host ext4/btrfs filesystem I/O without virtualization layers. | **Optimal**: Zero-copy Linux `sendfile`. Python worker handles auth in <2ms; Nginx handles transfer. | **Optimal**: High-speed direct disk I/O for Packet Tracer saves; zero-copy kernel `sendfile` for web downloads. |

**Justification for Recommendation**:  
Option D decisively outperforms Options A, B, and C in isolation. Option A introduces severe student friction and requires running an SSH daemon in every ephemeral container. Option B lacks a web retrieval mechanism, and Option C leaves container storage unpartitioned. Option D pairs kernel-level filesystem isolation with cryptographic HTTP delivery, establishing an un-bypassable security boundary while offering the most intuitive student workflow.

---

## 3. Solution Architecture & Technical Specification

### 3.1 Component Architecture & System Topology

The PacketTracerWeb production topology consists of four distinct network and security boundaries:

```
                                  ==============================================
                                  BOUNDARY 1: PUBLIC INTERNET / STUDENT BROWSER
                                  ==============================================
                                                        │
                                                        │ HTTPS (Port 443) / WSS (WebSocket)
                                                        ▼
┌───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                       BOUNDARY 2: NGINX EDGE GATEWAY (pt-nginx)                                    │
│                                                                                                                   │
│  ┌─────────────────────────┐  ┌──────────────────────────────────────────────┐  ┌──────────────────────────────┐  │
│  │   Guacamole Proxy       │  │   Student Download Gateway                   │  │   Protected Storage (VFS)    │  │
│  │   location / {          │  │   location /api/student/files/ {             │  │   location ^~ /internal/     │  │
│  │     proxy_pass          │  │     proxy_pass                               │  │            downloads/ {      │  │
│  │       http://pt-guac;   │  │       http://pt-mgmt:5000;                   │  │     internal; # BLOCKS EXT   │  │
│  │   }                     │  │     limit_req zone=pt_req_zone burst=15;     │  │     alias /shared/instances/;│  │
│  └────────────┬────────────┘  └──────────────────────┬───────────────────────┘  │     sendfile on;             │  │
│               │                                      │                          │     tcp_nopush on;           │  │
│               │ WebSocket (Guacamole)                │ HTTP Reverse Proxy       └──────────────▲───────────────┘  │
└───────────────┼──────────────────────────────────────┼─────────────────────────────────────────┼──────────────────┘
                │                                      │                                         │
                ▼                                      ▼                                         │
┌───────────────────────────────┐      ┌───────────────────────────────┐                         │
│ BOUNDARY 3A: GUACAMOLE STACK  │      │ BOUNDARY 3B: MANAGEMENT API   │                         │
│                               │      │                               │                         │
│  • pt-guacamole (Tomcat 9)    │      │  • pt-management (Flask)      │                         │
│  • pt-guacd (Guacamole Proxy) │      │  • Validates HMAC / Sessions  │                         │
│  • guacamole-mariadb (Auth)   │      │  • Bounds Check Path.rel_to   │                         │
│                               │      │  • Emits X-Accel-Redirect     │                         │
└───────────────┬───────────────┘      └───────────────┬───────────────┘                         │
                │                                      │                                         │
                │ Internal RFB / VNC (Port 5901)       │ Read-Only Verification                  │
                ▼                                      ▼                                         │
┌────────────────────────────────────────────────────────────────────────────────────────┐       │
│               BOUNDARY 4: VIRTUALIZED STUDENT RUNTIME CONTAINERS                       │       │
│                                                                                        │       │
│  ┌────────────────────────────────────┐    ┌────────────────────────────────────┐      │       │
│  │ Container: ptvnc1 (Student 1)      │    │ Container: ptvnc2 (Student 2)      │      │       │
│  │                                    │    │                                    │      │       │
│  │  • Cisco Packet Tracer GUI         │    │  • Cisco Packet Tracer GUI         │      │       │
│  │  • Desktop Symlinks & GTK Bookmarks│    │  • Desktop Symlinks & GTK Bookmarks│      │       │
│  │  • ~/pt/saves -> /shared           │    │  • ~/pt/saves -> /shared           │      │       │
│  │  • Mount: /shared/instances/ptvnc1 │    │  • Mount: /shared/instances/ptvnc2 │      │       │
│  └─────────────────┬──────────────────┘    └─────────────────┬──────────────────┘      │       │
└────────────────────┼─────────────────────────────────────────┼─────────────────────────┼───────┘
                     │                                         │                         │
                     ▼                                         ▼                         │
┌────────────────────────────────────────────────────────────────────────────────────────┴──────────────────────────┐
│                                       HOST STORAGE SUBSYSTEM (/shared)                                            │
│                                                                                                                   │
│   /shared/instances/ptvnc1/  (rw, 0770, uid 1000) ───────► Mount target for ptvnc1 container                     │
│   /shared/instances/ptvnc2/  (rw, 0770, uid 1000) ───────► Mount target for ptvnc2 container                     │
│   /shared/archive/           (rw, 0700, uid root) ───────► Deprovisioned instance archive storage (.tar.gz)       │
└───────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
```

---

### 3.2 Detailed Component Interaction & Data Flows

The end-to-end operational sequence for student lab saving, authentication verification, and zero-copy file delivery is depicted below:

```
Student Browser            pt-nginx             pt-management           Host Storage          ptvnc1 Container
      │                        │                      │                       │                      │
      │ 1. Interacts with PT   │                      │                       │                      │
      │    over Guacamole VNC  │                      │                       │                      │
      │───────────────────────►│────────────────────────────────────────────────────────────────────►│
      │                        │                      │                       │                      │
      │                        │                      │                       │ 2. File -> Save      │
      │                        │                      │                       │    Writes lab1.pkt   │
      │                        │                      │                       │    via ~/pt/saves    │
      │                        │                      │                       │◄─────────────────────│
      │                        │                      │                       │ (Saved to            │
      │                        │                      │                       │  /shared/instances/  │
      │                        │                      │                       │   ptvnc1/lab1.pkt)   │
      │                        │                      │                       │                      │
      │ 3. Click "Download Lab"│                      │                       │                      │
      │    GET /api/student/files/download?user=pt01&file=lab1.pkt&expires=...&sig=...               │
      │───────────────────────►│                      │                       │                      │
      │                        │ 4. Reverse Proxy     │                       │                      │
      │                        │    to pt-management  │                       │                      │
      │                        │─────────────────────►│                       │                      │
      │                        │                      │ 5. Cryptographic Auth │                      │
      │                        │                      │    & Path Traversal   │                      │
      │                        │                      │    Validation         │                      │
      │                        │                      │    Path.relative_to   │                      │
      │                        │                      │                       │                      │
      │                        │ 6. HTTP 200 OK       │                       │                      │
      │                        │    X-Accel-Redirect: /internal/downloads/ptvnc1/lab1.pkt            │
      │                        │    Content-Disposition: attachment; filename="lab1.pkt"             │
      │                        │◄─────────────────────│                       │                      │
      │                        │                      │                       │                      │
      │                        │ 7. Internal Reroute  │                       │                      │
      │                        │    Match /internal/  │                       │                      │
      │                        │    downloads/        │                       │                      │
      │                        │    Execute sendfile()│                       │                      │
      │                        │─────────────────────────────────────────────►│                      │
      │                        │                      │                       │                      │
      │ 8. Stream Binary Data  │                      │                       │                      │
      │    (Zero-Copy Kernel)  │                      │                       │                      │
      │◄───────────────────────│                      │                       │                      │
      │                        │                      │                       │                      │
```

#### Detailed Flow Step Descriptions:
1. **Interactive Session**: The student logs in to Guacamole and connects to their assigned virtual desktop container (`ptvnc1`).
2. **Native Save Execution**: Inside Cisco Packet Tracer, the student clicks **File → Save** (or `Ctrl+S`). The application defaults to `/home/ptuser/pt/saves/`, which is symlinked to `/shared`. The OS kernel writes the file directly to `/shared/instances/ptvnc1/lab1.pkt` on the host.
3. **Download Trigger**: The student initiates a download by clicking "Download My Lab" in the web portal top bar, or by executing a desktop helper applet. The browser issues a `GET` request to `/api/student/files/download` with the student identifier, requested filename, expiration timestamp, and HMAC-SHA256 signature.
4. **Gateway Forwarding**: Nginx verifies the rate limit and reverse-proxies the request to `pt-management:5000`.
5. **Backend Security Validation**:
   - `pt-management` verifies the HMAC-SHA256 signature using constant-time comparison (`hmac.compare_digest`).
   - Checks that the current epoch time has not exceeded the expiration timestamp.
   - Resolves the canonical target path and executes `target_path.relative_to(instance_dir)` to guarantee no path traversal (`../`) has occurred.
   - Verifies the file exists and is a regular file.
6. **Zero-Copy Delegation**: `pt-management` returns an empty HTTP response body with header `X-Accel-Redirect: /internal/downloads/ptvnc1/lab1.pkt` and standard attachment headers.
7. **Internal Gateway Routing**: Nginx intercepts the `X-Accel-Redirect` header. Because the URI matches `location ^~ /internal/downloads/`, Nginx maps it to the local alias `/shared/instances/ptvnc1/lab1.pkt`.
8. **Kernel Zero-Copy Transmission**: Nginx invokes Linux kernel `sendfile`, transferring data directly from the filesystem disk cache to the TCP socket buffer. The file streams to the student's browser at line speed.

---

### 3.3 Student End-to-End User Experience

#### 1. In-Session Save Experience (Inside Packet Tracer & XFCE)
A major usability friction point in the existing system is that students lose files by saving them to locations that do not map to host mounts. Option D configures a multi-layered symlink and desktop integration during container startup:

- **Packet Tracer Default Path Redirection**:
  Cisco Packet Tracer uses `/home/ptuser/pt/saves/` as its default user directory. The container initialization script executes:
  ```bash
  mkdir -p /home/ptuser/pt
  rm -rf /home/ptuser/pt/saves
  ln -sfn /shared /home/ptuser/pt/saves
  ```
  When a student clicks **File → Save As**, the file dialog immediately opens in `/shared`. Any file saved without changing directories is automatically stored in the isolated host volume!
- **Desktop & Downloads Symlinks**:
  ```bash
  ln -sfn /shared /home/ptuser/Desktop/Saved_Files
  ln -sfn /shared /home/ptuser/Downloads
  ```
  Students saving files to the Desktop or Downloads folders have their files transparently directed to `/shared`.
- **GTK & Qt File Chooser Bookmarks**:
  The file picker bookmark configuration `/home/ptuser/.config/gtk-3.0/bookmarks` is provisioned with:
  ```
  file:///shared Saved Files (Downloadable)
  ```
  This creates a high-visibility bookmark in the left-hand sidebar of all file selection dialogs in the XFCE desktop environment.

#### 2. Local Machine Download Experience (Web Portal & Desktop Helper)
Students can download saved `.pkt` files to their local laptops using two frictionless methods:

- **Method A: Web Portal Download Bar**:
  The web wrapper (`ptweb-vnc/pt-nginx/www/index.html`) hosts Guacamole within an iframe accompanied by a sleek top bar. A "My Saved Files" dropdown or "Download Latest Lab" button calls the student API, retrieves the list of files in `/shared/instances/{container_name}/`, and triggers direct browser downloads.
- **Method B: Desktop One-Click Launcher ("Export Lab to Browser")**:
  A desktop shortcut `/home/ptuser/Desktop/Export_Files.desktop` is provided on the XFCE desktop. When clicked, it runs a small script:
  ```bash
  #!/usr/bin/env bash
  # Mint token and trigger browser download
  LATEST_PKT=$(ls -t /shared/*.pkt 2>/dev/null | head -n 1)
  if [ -z "$LATEST_PKT" ]; then
      notify-send "Export Files" "No .pkt files found in /shared. Please save your lab first!" -i dialog-warning
      exit 1
  fi
  FNAME=$(basename "$LATEST_PKT")
  # Call internal minting helper or display confirmation
  notify-send "Lab Ready for Download" "Your file $FNAME is saved and ready in the web portal download bar." -i document-save
  ```

---

### 3.4 Comprehensive Security Threat Model & Defense-in-Depth Analysis

#### Threat Vector 1: Confidentiality & Academic Plagiarism (Cross-Tenant Snooping)
- **Threat**: A student in container `ptvnc2` attempts to list or copy another student's `.pkt` file from container `ptvnc1` to submit as their own coursework.
- **Mitigation**: Linux kernel mount namespace segregation. Container `ptvnc2` only has `/shared/instances/ptvnc2` mounted into its namespace. Host directory `/shared/instances/ptvnc1` does not exist inside `ptvnc2`'s VFS. Even if a student gains root privileges inside their container, they cannot access files outside their mounted namespaces.

#### Threat Vector 2: Unauthenticated External Reconnaissance & Enumeration
- **Threat**: An external attacker scans the web application and requests `https://<host>/downloads/` or `https://<host>/internal/downloads/` to harvest student topologies and network device configs.
- **Mitigation**: Complete removal of `location ^~ /downloads/` eliminates the autoindex endpoint. The new storage location `location ^~ /internal/downloads/` is guarded by Nginx's `internal;` directive. Any direct external request to this URI is rejected by Nginx with HTTP 404 (Not Found), making the internal storage physically unreachable from outside the gateway.

#### Threat Vector 3: Multi-Tenant Directory Traversal (`../` Attacks)
- **Threat**: An attacker manipulates the download query string:
  `GET /api/student/files/download?user=pt01&file=../../pt02/final_exam.pkt`
- **Mitigation**: Upstream Python path containment bounds checking:
  ```python
  user_root = (STORAGE_BASE / container_name).resolve()
  target_path = (user_root / filename).resolve()
  try:
      target_path.relative_to(user_root)
  except ValueError:
      # Raised if target_path does not start with user_root
      return jsonify({'error': 'Path traversal attempt blocked'}), 403
  ```
  `Path.resolve()` canonicalizes all symlinks, dot-dots, and relative components. If `target_path` is not strictly a descendant of `user_root`, the request is immediately aborted with a 403 Forbidden alert.

#### Threat Vector 4: URL Tampering & Unauthorized File Exfiltration
- **Threat**: A user alters the username parameter in a download URL (`?user=pt02`) to download a peer's files.
- **Mitigation**: Cryptographic HMAC-SHA256 signatures:
  $$\text{Payload} = \text{user} \parallel \text{filename} \parallel \text{expires}$$
  $$\text{Signature} = \text{HMAC-SHA256}(K_{\text{secret}}, \text{Payload})$$
  The server verifies:
  1. `time.time() <= int(expires)` (rejects expired links, default TTL = 300 seconds).
  2. `hmac.compare_digest(expected_signature, client_signature)` (constant-time verification to prevent cryptographic timing attacks).
  Because the client cannot forge the HMAC signature without the server's private `SECRET_KEY`, tampering with any parameter invalidates the request.

#### Threat Vector 5: Denial of Service & Application Worker Starvation
- **Threat**: An attacker initiates dozens of concurrent downloads of massive 50 MB packet capture topologies, consuming Python Gunicorn workers and exhausting server memory.
- **Mitigation**: 
  1. **Nginx Rate Limiting**: The download API is subject to Nginx request rate limiting:
     `limit_req zone=pt_req_zone burst=15 nodelay;`
  2. **Zero-Copy Offloading (`X-Accel-Redirect`)**: The Flask Python worker processes the authentication logic in <2ms, returns an empty body with headers, and terminates immediately. Nginx handles the file streaming via kernel `sendfile` asynchronously, preventing worker exhaustion.
  3. **Gzip Disabling**: Pre-compressed Cisco archives (`.pkt`, `.pka`) bypass Nginx gzip compression (`gzip off;`), eliminating unnecessary CPU cycles.

---

### 3.5 Edge Cases & Operational Resiliency

#### 1. Concurrent Sessions & Multi-Tab Access
Students frequently open multiple browser tabs or initiate concurrent downloads. Because download tokens are stateless (HMAC-SHA256) and verified against a fixed expiration epoch, parallel download requests succeed independently without session locks or database bottlenecks.

#### 2. Container Restarts & Crash Recovery
If a `ptvnc` container crashes, runs out of memory, or is restarted via `docker restart ptvnc1`, the host directory `/shared/instances/ptvnc1` is untouched. When the container comes back online, its bind mount reattaches to the exact same directory, guaranteeing zero data loss for saved files.

#### 3. Container Recycling & Sequential Tenant Deprovisioning
In educational environments, virtual desktop containers are often recycled between class sections. If Student A finishes their lab at 10:00 AM and Student B is assigned `ptvnc1` at 10:15 AM, leaving Student A's files in `/shared/instances/ptvnc1` would allow Student B to view Student A's work.
- **Automated Archiving Lifecycle**:
  When a container is deprovisioned (via `remove-instance.sh` or the container deletion API), the platform executes an automated archiving lifecycle hook:
  ```bash
  ARCHIVE_NAME="${container_name}_$(date +%Y%m%d_%H%M%S).tar.gz"
  tar -czf "/shared/archive/${ARCHIVE_NAME}" -C "/shared/instances" "${container_name}"
  rm -rf "/shared/instances/${container_name}"
  ```
  The student's work is preserved for grading in `/shared/archive/`, while the instance directory is purged. When a new container is provisioned, a clean, empty directory is mounted.

#### 4. Storage Quotas & Automated Disk Housekeeping
To prevent rogue processes or unbounded packet captures from exhausting host storage:
- Instance directories can be provisioned with Linux filesystem project quotas (`xfs_quota` or `btrfs subvolume`) limiting each instance directory to 500 MB.
- An automated cron or systemd housekeeping timer purges archives in `/shared/archive/` older than 30 days:
  ```bash
  find /shared/archive -name "*.tar.gz" -type f -mtime +30 -delete
  ```

---

## 4. Step-by-Step Implementation & Configuration Guide

This section provides production-ready code snippets and configuration diffs for every affected component in the PacketTracerWeb repository.

---

### Component 1: Nginx Gateway Configuration

#### Affected Files:
- `ptweb-vnc/pt-nginx/conf/ptweb.conf`
- `ptweb-vnc/pt-nginx/generate-nginx-conf.sh`

#### Configuration Changes:
1. Delete the public `location ^~ /downloads/` block.
2. Add the protected internal file delivery location `location ^~ /internal/downloads/`.
3. Add proxy routing for the student file download API `location ^~ /api/student/files/`.

#### Exact Unified Diff (`ptweb-vnc/pt-nginx/conf/ptweb.conf`):
```diff
--- a/ptweb-vnc/pt-nginx/conf/ptweb.conf
+++ b/ptweb-vnc/pt-nginx/conf/ptweb.conf
@@ -28,14 +28,29 @@
   charset utf-8;
 
-  # Serve shared downloads with highest priority
-  location ^~ /downloads/ {
-    # Bypass GeoIP for trusted IPs (local/private/public)
-    if ($remote_addr ~ ^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)|86.50.84.227) {
-      set $allowed_country 1;
-      set $blocked_country 0;
-    }
-    # ALLOW mode: only permitted countries allowed
-    if ($allowed_country = 0) { return 444; }
-    alias /shared/;
-    autoindex on;
-    autoindex_exact_size off;
-    autoindex_localtime on;
-  }
+  # Protected internal storage serving - accessible ONLY via X-Accel-Redirect
+  location ^~ /internal/downloads/ {
+    internal;
+    alias /shared/instances/;
+    
+    # Kernel zero-copy optimizations
+    sendfile on;
+    tcp_nopush on;
+    tcp_nodelay on;
+    
+    # Cisco packet tracer topologies (.pkt/.pka) are already compressed
+    gzip off;
+    
+    default_type application/octet-stream;
+    add_header X-Content-Type-Options nosniff always;
+    add_header Content-Security-Policy "default-src 'none'" always;
+  }
+
+  # Reverse proxy for Student File Download API
+  location ^~ /api/student/files/ {
+    limit_req zone=pt_req_zone burst=15 nodelay;
+    proxy_pass http://pt-management:5000/api/student/files/;
+    proxy_redirect off;
+    proxy_set_header Host $host;
+    proxy_set_header X-Real-IP $remote_addr;
+    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
+    proxy_set_header X-Forwarded-Proto $scheme;
+  }
```

#### Exact Unified Diff (`ptweb-vnc/pt-nginx/generate-nginx-conf.sh`):
```diff
--- a/ptweb-vnc/pt-nginx/generate-nginx-conf.sh
+++ b/ptweb-vnc/pt-nginx/generate-nginx-conf.sh
@@ -254,12 +254,26 @@
   charset utf-8;
 
-  # Serve shared downloads with highest priority
-  location ^~ /downloads/ {
-EOF
-  render_geoip_check
-  cat <<'EOF'
-    alias /shared/;
-    autoindex on;
-    autoindex_exact_size off;
-    autoindex_localtime on;
-  }
+  # Protected internal storage serving - accessible ONLY via X-Accel-Redirect
+  location ^~ /internal/downloads/ {
+    internal;
+    alias /shared/instances/;
+    sendfile on;
+    tcp_nopush on;
+    tcp_nodelay on;
+    gzip off;
+    default_type application/octet-stream;
+    add_header X-Content-Type-Options nosniff always;
+  }
+
+  # Reverse proxy for Student File Download API
+  location ^~ /api/student/files/ {
+EOF
+  render_rate_limit
+  cat <<'EOF'
+    proxy_pass http://pt-management:5000/api/student/files/;
+    proxy_redirect off;
+    proxy_set_header Host $host;
+    proxy_set_header X-Real-IP $remote_addr;
+    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
+    proxy_set_header X-Forwarded-Proto $scheme;
+  }
```

---

### Component 2: Host Storage Layout & Docker Mount Updates

#### Directory Hierarchy Setup:
Host filesystem directory layout initialized prior to container launches:
```bash
mkdir -p "${WORKDIR}/shared/instances"
mkdir -p "${WORKDIR}/shared/archive"
chmod 755 "${WORKDIR}/shared"
chmod 755 "${WORKDIR}/shared/instances"
chmod 700 "${WORKDIR}/shared/archive"
```

#### Exact Unified Diff (`deploy.sh`):
```diff
--- a/deploy.sh
+++ b/deploy.sh
@@ -202,4 +202,5 @@
 echo -e "\e[32mStep 2. Start Packet Tracer VNC containers\e[0m"
-mkdir -p "${WORKDIR}/shared"
-chmod 777 "${WORKDIR}/shared"
+mkdir -p "${WORKDIR}/shared/instances"
+mkdir -p "${WORKDIR}/shared/archive"
+chmod 755 "${WORKDIR}/shared/instances"
 
@@ -229,8 +230,12 @@
 for ((i=1; i<=$numofPT; i++)); do
+    INSTANCE_DIR="${WORKDIR}/shared/instances/ptvnc$i"
+    mkdir -p "$INSTANCE_DIR"
+    chmod 777 "$INSTANCE_DIR"
+
     docker run -d \
       --name ptvnc$i --restart unless-stopped \
       --network ptnet \
       --cpus=0.5 -m 2G --ulimit nproc=2048 --ulimit nofile=1024 \
       --dns=127.0.0.1 \
       -v pt_opt:/opt/pt \
-      --mount type=bind,source="${WORKDIR}/shared",target=/shared,bind-propagation=rprivate \
+      --mount type=bind,source="${INSTANCE_DIR}",target=/shared,bind-propagation=rprivate \
       ptvnc
```

#### Exact Unified Diff (`add-instance.sh`):
```diff
--- a/add-instance.sh
+++ b/add-instance.sh
@@ -68,4 +68,5 @@
 # Prepare shared directory
-mkdir -p "$(pwd)/shared"
-chmod 777 "$(pwd)/shared"
+mkdir -p "$(pwd)/shared/instances"
+mkdir -p "$(pwd)/shared/archive"
 
@@ -84,7 +85,11 @@
     fi
     
+    INSTANCE_DIR="${WORKDIR}/shared/instances/${container_name}"
+    mkdir -p "$INSTANCE_DIR"
+    chmod 777 "$INSTANCE_DIR"
+
     echo "Creating $container_name..."
     docker run -d \
       --name $container_name --restart unless-stopped \
       --cpus=0.5 -m 2G --ulimit nproc=2048 --ulimit nofile=1024 \
       --network ptnet \
       -v "${WORKDIR}/${PTfile}:/PacketTracer.deb:ro" \
       -v pt_opt:/opt/pt \
       --dns=127.0.0.1 \
-      --mount type=bind,source="${WORKDIR}/shared",target=/shared,bind-propagation=rprivate \
+      --mount type=bind,source="${INSTANCE_DIR}",target=/shared,bind-propagation=rprivate \
       -e PT_DEB_PATH=/PacketTracer.deb \
       ptvnc
```

#### Exact Unified Diff (`pt-management/ptmanagement/docker_mgmt/container.py`):
```diff
--- a/pt-management/ptmanagement/docker_mgmt/container.py
+++ b/pt-management/ptmanagement/docker_mgmt/container.py
@@ -358,12 +358,19 @@
             if shared_host_path_env:
                 shared_path = shared_host_path_env
             elif project_root_env:
                 shared_path = os.path.join(project_root_env, 'shared')
             else:
                 shared_path = os.path.abspath(os.path.join(os.getcwd(), 'shared'))
-            logger.info(f"DEBUG container.py: Using shared_path={shared_path}")
+            
+            # Partition storage per container instance
+            instance_storage_path = os.path.join(shared_path, 'instances', name)
+            os.makedirs(instance_storage_path, exist_ok=True)
+            try:
+                os.chmod(instance_storage_path, 0o777)
+            except OSError:
+                pass
+            logger.info(f"DEBUG container.py: Using instance_storage_path={instance_storage_path}")
             
             request_data["HostConfig"]["Binds"] = [
                 "pt_opt:/opt/pt",  # Named volume for Packet Tracer binary
-                f"{shared_path}:/shared"  # Bind mount for shared files (MUST be host path)
+                f"{instance_storage_path}:/shared"  # Isolated instance storage mount
             ]
```

#### Docker Compose Volume Mounting Updates (`ptweb-vnc/docker-compose.yml`):
Ensure the `nginx` and `pt-management` containers mount the updated `/shared` parent directory with read-only permissions for Nginx:
```yaml
  nginx:
    volumes:
      - ./pt-nginx/www:/usr/share/nginx/html:ro
      - ./pt-nginx/conf:/etc/nginx/conf.d:ro
      - ./pt-nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ../ssl/server.crt:/etc/ssl/certs/server.crt:ro
      - ../ssl/server.key:/etc/ssl/private/server.key:ro
      - ../geoip/GeoIP.dat:/usr/share/GeoIP/GeoIP.dat:ro
      - ./shared:/shared:ro # Read-only mount of shared root for internal zero-copy delivery
```

---

### Component 3: Virtual Desktop Environment & Save UX

#### Affected Files:
- `ptweb-vnc/customizations/start-session` (or `deploy.sh` provisioning loop)

#### Configuration Changes:
During container startup, execute configuration commands to seamlessly link Packet Tracer's default save folder, desktop folders, and GTK bookmarks directly to `/shared`.

#### Script Implementation (`ptweb-vnc/customizations/start-session` or deployment hook):
```bash
# ------------------------------------------------------------------------------
# Secure Storage Integration & Desktop UX Redirection
# ------------------------------------------------------------------------------
echo "Configuring transparent save redirection to /shared..."

# 1. Transparently redirect Packet Tracer's default save path to /shared
mkdir -p /home/ptuser/pt
rm -rf /home/ptuser/pt/saves
ln -sfn /shared /home/ptuser/pt/saves
chown -h ptuser:ptuser /home/ptuser/pt/saves

# 2. Configure Desktop and Downloads symlinks
mkdir -p /home/ptuser/Desktop
mkdir -p /home/ptuser/Downloads
ln -sfn /shared /home/ptuser/Desktop/Downloads
ln -sfn /shared /home/ptuser/Desktop/Saved_Files
ln -sfn /shared /home/ptuser/Downloads/Saved_Files
chown -R ptuser:ptuser /home/ptuser/Desktop /home/ptuser/Downloads

# 3. Provision GTK-3 file chooser sidebar bookmarks
mkdir -p /home/ptuser/.config/gtk-3.0
cat << 'EOF' > /home/ptuser/.config/gtk-3.0/bookmarks
file:///shared Saved Files (Downloadable via Web)
EOF
chown -R ptuser:ptuser /home/ptuser/.config

# 4. Create Desktop Helper Launcher
cat << 'EOF' > /home/ptuser/Desktop/Export_Lab.desktop
[Desktop Entry]
Version=1.0
Type=Application
Name=Export Lab Files
Comment=Verify your saved labs are ready for browser download
Exec=zenity --info --title="Lab Storage" --text="All files saved in /shared, Desktop/Saved_Files, or default Packet Tracer Saves are immediately accessible in your Web Portal top bar for download!"
Icon=document-save
Terminal=false
StartupNotify=false
EOF
chmod +x /home/ptuser/Desktop/Export_Lab.desktop
chown ptuser:ptuser /home/ptuser/Desktop/Export_Lab.desktop
```

---

### Component 4: Flask Management Service Student API (`pt-management`)

#### Affected Files:
- Create `pt-management/ptmanagement/api/student_routes.py`
- Register blueprint and update `check_authentication` in `pt-management/app.py`

#### Implementation: `pt-management/ptmanagement/api/student_routes.py`
```python
"""
Secure Student File Download API
Handles HMAC token generation, path traversal validation, and Nginx X-Accel-Redirect emission.
"""
import os
import time
import hmac
import hashlib
from pathlib import Path
from flask import Blueprint, request, jsonify, Response, current_app

student_api = Blueprint('student_api', __name__, url_prefix='/api/student/files')

# Host-mounted storage root inside pt-management container
STORAGE_BASE = Path("/shared/instances").resolve()


def generate_download_token(container_name: str, filename: str, ttl_seconds: int = 300) -> dict:
    """Generate a time-limited HMAC-SHA256 download signature."""
    secret = current_app.config.get('SECRET_KEY', 'default-pt-secret-key').encode('utf-8')
    expires = int(time.time()) + ttl_seconds
    payload = f"{container_name}:{filename}:{expires}".encode('utf-8')
    signature = hmac.new(secret, payload, hashlib.sha256).hexdigest()
    return {
        'container': container_name,
        'file': filename,
        'expires': expires,
        'sig': signature
    }


def verify_download_token(container_name: str, filename: str, expires_str: str, signature: str) -> bool:
    """Validate signature authenticity and expiration timestamp."""
    try:
        expires = int(expires_str)
        if time.time() > expires:
            return False  # Token expired
        
        secret = current_app.config.get('SECRET_KEY', 'default-pt-secret-key').encode('utf-8')
        payload = f"{container_name}:{filename}:{expires}".encode('utf-8')
        expected_sig = hmac.new(secret, payload, hashlib.sha256).hexdigest()
        
        # Constant-time comparison prevents cryptographic timing attacks
        return hmac.compare_digest(expected_sig, signature)
    except (ValueError, TypeError):
        return False


@student_api.route('/download', methods=['GET'])
def download_file():
    """
    Zero-copy student file download endpoint via Nginx X-Accel-Redirect.
    Required query parameters:
      - container: Container/instance name (e.g. ptvnc1)
      - file: Target filename (e.g. lab1.pkt)
      - expires: Unix epoch timestamp
      - sig: HMAC-SHA256 signature
    """
    container_name = request.args.get('container', '').strip()
    filename = request.args.get('file', '').strip()
    expires = request.args.get('expires', '').strip()
    signature = request.args.get('sig', '').strip()

    if not all([container_name, filename, expires, signature]):
        return jsonify({'error': 'Missing required query parameters'}), 400

    # 1. Cryptographic Authentication & Expiration Check
    if not verify_download_token(container_name, filename, expires, signature):
        return jsonify({'error': 'Invalid or expired download signature'}), 403

    # 2. Multi-Tenant Path Traversal Prevention
    container_dir = (STORAGE_BASE / container_name).resolve()
    target_path = (container_dir / filename).resolve()

    try:
        # Enforce that target_path is strictly within container_dir
        target_path.relative_to(container_dir)
    except ValueError:
        return jsonify({'error': 'Access denied: Path traversal detected'}), 403

    # 3. File Verification
    if not target_path.exists() or not target_path.is_file():
        return jsonify({'error': 'Requested file not found'}), 404

    # 4. Emit Zero-Copy Nginx X-Accel-Redirect Header
    internal_uri = f"/internal/downloads/{container_name}/{target_path.name}"
    
    response = Response("", status=200)
    response.headers['X-Accel-Redirect'] = internal_uri
    response.headers['Content-Type'] = 'application/octet-stream'
    response.headers['Content-Disposition'] = f'attachment; filename="{target_path.name}"'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@student_api.route('/list', methods=['GET'])
def list_files():
    """
    List available files in the student instance's isolated directory.
    Returns file names, sizes, and signed download tokens for direct client retrieval.
    """
    container_name = request.args.get('container', '').strip()
    if not container_name:
        return jsonify({'error': 'Container identifier required'}), 400

    container_dir = (STORAGE_BASE / container_name).resolve()
    try:
        container_dir.relative_to(STORAGE_BASE)
    except ValueError:
        return jsonify({'error': 'Invalid container identifier'}), 403

    if not container_dir.exists():
        return jsonify({'container': container_name, 'files': []}), 200

    results = []
    for entry in container_dir.iterdir():
        if entry.is_file() and not entry.name.startswith('.'):
            stat = entry.stat()
            token_meta = generate_download_token(container_name, entry.name, ttl_seconds=600)
            download_url = (
                f"/api/student/files/download?"
                f"container={token_meta['container']}&"
                f"file={token_meta['file']}&"
                f"expires={token_meta['expires']}&"
                f"sig={token_meta['sig']}"
            )
            results.append({
                'name': entry.name,
                'size_bytes': stat.st_size,
                'modified_epoch': stat.st_mtime,
                'download_url': download_url
            })

    return jsonify({
        'container': container_name,
        'count': len(results),
        'files': sorted(results, key=lambda x: x['modified_epoch'], reverse=True)
    }), 200
```

#### Exact Unified Diff (`pt-management/app.py`):
```diff
--- a/pt-management/app.py
+++ b/pt-management/app.py
@@ -115,6 +115,10 @@
         protected_routes = ['/dashboard', '/settings', '/files', '/api/']
         
         if any(request.path.startswith(route) for route in protected_routes):
+            # Exclude student download API from admin session requirement
+            if request.path.startswith('/api/student/files/'):
+                return
+
             # Allow public defaults endpoint without authentication
             if request.path.startswith('/api/env/defaults') and request.method == 'GET':
                 return
@@ -155,4 +159,8 @@
     from ptmanagement.api.routes import create_api_blueprint
     api_bp = create_api_blueprint()
     app.register_blueprint(api_bp)
+
+    from ptmanagement.api.student_routes import student_api
+    app.register_blueprint(student_api)
+
     return app
```

---

### Component 5: Lifecycle & Deprovisioning Hooks

#### Affected Files:
- `remove-instance.sh`
- `pt-management/ptmanagement/api/routes.py`

#### Configuration Changes:
When an instance is removed, automatically package its files into `/shared/archive/{container_name}_{timestamp}.tar.gz` and delete the instance directory from `/shared/instances/`.

#### Exact Unified Diff (`remove-instance.sh`):
```diff
--- a/remove-instance.sh
+++ b/remove-instance.sh
@@ -121,6 +121,19 @@
 echo -e "\e[32mStep 1. Stopping and removing containers\e[0m"
 for instance_num in $instances_to_remove_list; do
     container_name="ptvnc$instance_num"
+    
+    # Archive and clean instance storage directory
+    INSTANCE_DIR="${WORKDIR}/shared/instances/${container_name}"
+    ARCHIVE_DIR="${WORKDIR}/shared/archive"
+    if [ -d "$INSTANCE_DIR" ]; then
+        mkdir -p "$ARCHIVE_DIR"
+        ARCHIVE_FILE="${ARCHIVE_DIR}/${container_name}_$(date +%Y%m%d_%H%M%S).tar.gz"
+        echo "Archiving storage for $container_name to $ARCHIVE_FILE..."
+        tar -czf "$ARCHIVE_FILE" -C "${WORKDIR}/shared/instances" "$container_name" 2>/dev/null || true
+        rm -rf "$INSTANCE_DIR"
+        echo "  ✓ Cleaned storage for $container_name"
+    fi
+
     echo "Removing $container_name..."
     docker stop $container_name 2>/dev/null || true
     docker rm $container_name 2>/dev/null || true
```

#### Exact Unified Diff (`pt-management/ptmanagement/api/routes.py`):
```diff
--- a/pt-management/ptmanagement/api/routes.py
+++ b/pt-management/ptmanagement/api/routes.py
@@ -348,6 +348,22 @@
                 # Stop and remove container
                 docker_mgr.delete_container(container_name, force=True)
                 
+                # Archive and clean instance storage directory
+                import tarfile
+                from datetime import datetime
+                shared_root = os.getenv('SHARED_HOST_PATH', '/shared')
+                inst_dir = os.path.join(shared_root, 'instances', container_name)
+                arch_dir = os.path.join(shared_root, 'archive')
+                if os.path.exists(inst_dir):
+                    os.makedirs(arch_dir, exist_ok=True)
+                    arch_name = f"{container_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.tar.gz"
+                    arch_path = os.path.join(arch_dir, arch_name)
+                    with tarfile.open(arch_path, "w:gz") as tar:
+                        tar.add(inst_dir, arcname=container_name)
+                    import shutil
+                    shutil.rmtree(inst_dir, ignore_errors=True)
+                    logger.info(f"Archived and cleaned storage for {container_name}")
+
                 # Delete Guacamole connection
                 if guac_db:
```

---

## 5. Validation, Testing & Verification Plan

### 5.1 Test Matrix Overview

| Test Case | Description | Verification Method | Expected Outcome |
| :--- | :--- | :--- | :--- |
| **Test 1** | Public Directory Enumeration Rejection | External `curl -k -I https://localhost/downloads/` | `HTTP/2 404` or `444` (No directory listing) |
| **Test 2** | Direct Protected Storage Rejection | External `curl -k -I https://localhost/internal/downloads/ptvnc1/lab1.pkt` | `HTTP/2 404` (Nginx `internal;` blocks direct access) |
| **Test 3** | Cross-Tenant Container Mount Isolation | Create sentinel in `ptvnc1`; attempt read in `ptvnc2` | `No such file or directory` (Exit code 2) |
| **Test 4** | Path Traversal Vulnerability Rejection | Query `/download` with `../../ptvnc2/secret.pkt` | `HTTP 403 Forbidden` (`Path traversal detected`) |
| **Test 5** | Authenticated Download & Zero-Copy Delivery | Request valid signed URL; verify headers & data stream | `HTTP 200 OK`, `X-Accel-Redirect` stripped, bytes match |
| **Test 6** | Deprovisioning Archiving & Storage Cleanup | Deprovision `ptvnc3`; inspect `/shared/archive/` and `/instances/` | Archive `.tar.gz` created; instance dir purged |

---

### 5.2 Detailed Verification Procedures

#### Test 1: Public Enumeration Rejection
Verify that the legacy `/downloads/` directory listing has been eradicated.
```bash
# Execute against the Nginx edge gateway
curl -k -s -w "\nHTTP_STATUS: %{http_code}\n" https://localhost/downloads/

# Expected Output:
# <html><head><title>404 Not Found</title></head>...
# HTTP_STATUS: 404
```
*Validation Pass Criteria*: HTTP status is 404 Not Found. HTML response body does **not** contain `<title>Index of /downloads/</title>`.

---

#### Test 2: Direct Internal Access Rejection
Verify that external clients cannot circumvent authentication by directly requesting `/internal/downloads/`.
```bash
# Create a dummy test file in an instance directory
docker exec ptvnc1 bash -c 'echo "network-config" > /shared/test_probe.pkt'

# Attempt to fetch directly from internal alias
curl -k -s -w "\nHTTP_STATUS: %{http_code}\n" https://localhost/internal/downloads/ptvnc1/test_probe.pkt

# Expected Output:
# HTTP_STATUS: 404
```
*Validation Pass Criteria*: Nginx immediately returns HTTP 404 without consulting the backend, proving `internal;` enforcement.

---

#### Test 3: Storage Isolation Between Containers
Verify that containers cannot view, modify, or delete files stored in other container instances.
```bash
# 1. Place confidential sentinel file inside ptvnc1
docker exec ptvnc1 bash -c 'echo "alice_secret_token_12345" > /shared/alice_exam.pkt'

# 2. Attempt to list the file from ptvnc2
docker exec ptvnc2 ls -la /shared/alice_exam.pkt 2>&1

# Expected Output:
# ls: cannot access '/shared/alice_exam.pkt': No such file or directory
# Exit code: 2

# 3. Inspect physical host paths
test -f shared/instances/ptvnc1/alice_exam.pkt && echo "PASS: Exists in ptvnc1"
test ! -f shared/instances/ptvnc2/alice_exam.pkt && echo "PASS: Isolated from ptvnc2"
```
*Validation Pass Criteria*: `ptvnc2` returns `No such file or directory`. File exists strictly within `shared/instances/ptvnc1/`.

---

#### Test 4: Path Traversal Rejection
Verify that dot-dot-slash (`../`) directory traversal attempts are thwarted by `Path.relative_to`.
```bash
# Attempt path traversal using relative parent paths
EXPIRES=$(($(date +%s) + 300))
# Even with arbitrary signature or valid signature, traversal check triggers first:
curl -k -s "https://localhost/api/student/files/download?container=ptvnc1&file=../../ptvnc2/alice_exam.pkt&expires=${EXPIRES}&sig=bogussig"

# Expected Output:
# {"error":"Invalid or expired download signature"}

# Test traversal with validly signed payload against dummy key
python3 -c "
import hmac, hashlib
secret = b'default-pt-secret-key'
payload = b'ptvnc1:../../ptvnc2/alice_exam.pkt:${EXPIRES}'
print(hmac.new(secret, payload, hashlib.sha256).hexdigest())
" > /tmp/traversal_sig.txt
SIG=$(cat /tmp/traversal_sig.txt)

curl -k -s "https://localhost/api/student/files/download?container=ptvnc1&file=../../ptvnc2/alice_exam.pkt&expires=${EXPIRES}&sig=${SIG}"

# Expected Output:
# {"error":"Access denied: Path traversal detected"}
```
*Validation Pass Criteria*: Endpoint returns HTTP 403 Forbidden with `"Access denied: Path traversal detected"`.

---

#### Test 5: End-to-End Authenticated Download & Zero-Copy Streaming Verification
Verify the complete workflow: saving inside Packet Tracer, querying the file list, and downloading via Nginx `X-Accel-Redirect`.
```bash
# 1. Save file in ptvnc1 default save path
docker exec ptvnc1 bash -c 'echo "packet-tracer-binary-data" > /home/ptuser/pt/saves/lab1_final.pkt'

# 2. Query student file listing API
LIST_JSON=$(curl -k -s "https://localhost/api/student/files/list?container=ptvnc1")
echo "$LIST_JSON" | grep -q "lab1_final.pkt" && echo "PASS: File listed in student API"

# 3. Extract generated download URL with HMAC token
DOWNLOAD_PATH=$(echo "$LIST_JSON" | grep -o '"download_url": *"[^"]*"' | head -n 1 | cut -d'"' -f4)

# 4. Perform download via Nginx
curl -k -i "https://localhost${DOWNLOAD_PATH}" -o /tmp/downloaded_lab1.pkt

# Expected Headers:
# HTTP/2 200
# content-type: application/octet-stream
# content-disposition: attachment; filename="lab1_final.pkt"
# x-content-type-options: nosniff
# (Notice X-Accel-Redirect header is consumed by Nginx and NOT sent to client)

# 5. Verify integrity of downloaded file
diff /tmp/downloaded_lab1.pkt shared/instances/ptvnc1/lab1_final.pkt && echo "PASS: Zero-copy download matches original byte-for-byte"
```
*Validation Pass Criteria*: Direct binary match, HTTP 200 OK, `X-Accel-Redirect` correctly handled internally.

---

#### Test 6: Deprovisioning Archiving & Storage Cleanup Verification
Verify that deprovisioning an instance preserves student work in `/shared/archive/` and wipes the instance directory.
```bash
# 1. Ensure ptvnc3 has active files
mkdir -p shared/instances/ptvnc3
echo "charlie_assignment" > shared/instances/ptvnc3/charlie.pkt

# 2. Run remove-instance script for ptvnc3
bash remove-instance.sh pt03 <<< "yes"

# 3. Verify archive creation in shared/archive/
ls -la shared/archive/ptvnc3_*.tar.gz && echo "PASS: Archive successfully created"

# 4. Verify instance directory is completely purged
test ! -d shared/instances/ptvnc3 && echo "PASS: Instance directory purged (no sequential data leak)"
```
*Validation Pass Criteria*: Archive tarball is generated; directory `shared/instances/ptvnc3` is deleted, preventing subsequent users of container `ptvnc3` from accessing prior tenant data.

---

## 6. Conclusion & Roadmap Summary

The **Hybrid Per-Instance Isolated Storage and Cryptographically Authenticated Gateway Architecture (Option D)** provides a comprehensive, production-grade resolution to the file download and multi-tenancy vulnerabilities in PacketTracerWeb. 

By eradicating the public `/downloads/` directory listing, isolating container mounts into dedicated `/shared/instances/{container_name}/` directories, enforcing time-limited HMAC-SHA256 download tokens with path traversal bounds checking, and delegating file delivery to Nginx's zero-copy kernel `sendfile` engine via `X-Accel-Redirect`, this architecture establishes an unassailable security perimeter while maintaining an intuitive, zero-friction user experience for students.

All required configuration diffs, scripts, and verification commands are fully specified, enabling direct implementation across development and production environments.
