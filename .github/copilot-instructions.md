## Quick orientation

This repo runs multiple Cisco Packet Tracer instances inside Docker containers and exposes them via an Nginx + Guacamole web UI. The important runtime pieces are:

- `ptweb-vnc/` — Dockerfile, runtime helpers, and customization scripts used to build the Packet Tracer image.
- `ptweb-vnc/customizations/` — installs and runtime helpers (e.g. `runtime-install.sh`, `pt-install.sh`, `pt-detect.sh`).
- `ptweb-vnc/db-dump.sql` — initial Guacamole DB schema & data imported by deployment scripts.
- Top-level scripts (`deploy.sh`, `add-instance.sh`, `remove-instance.sh`, `tune_ptvnc.sh`, `generate-dynamic-connections.sh`, `test-deployment.sh`) — the canonical developer workflows.
- `pt-nginx/` — nginx config and static web UI (`pt-nginx/www`) used to expose Guacamole and the downloads folder.

If you need a quick local run: place the official Packet Tracer `.deb` in the repo root and run

    bash deploy.sh

This will build the Docker image (if needed), start MariaDB, guacd, guacamole and Nginx, then launch 2 Packet Tracer containers by default.

## Architecture notes for code-change agents

- Packet Tracer containers are started as `ptvnc1`, `ptvnc2`, ... (scripts use `PT_CONTAINER_BASE`, defaults to `ptvnc`). Search for `ptvnc` when inspecting scripts.
- Docker image name is consistently `ptvnc` across all scripts (`deploy.sh`, `add-instance.sh`, `start-full-stack.sh`). Built from `ptweb-vnc/Dockerfile`.
- The Guacamole stack uses a MariaDB dump (`ptweb-vnc/db-dump.sql`) to pre-populate connections. `generate-dynamic-connections.sh` regenerates connection rows when the number of PT instances changes.
- Shared files: `/shared` is bind-mounted into each PT container and is the recommended way for users to save `.pkt` files (web UI exposes `/downloads/`). Any code that touches file workflows should reference `/shared` and `pt-nginx/www`.

## Developer workflows & important commands (concrete)

- Build + smoke-check (fast):

    cd ptweb-vnc
    bash scripts/ci-smoke.sh

  The smoke script builds the image and verifies the Packet Tracer binary exists under `/opt/pt`.

- Full deploy (recommended for manual testing):

    bash deploy.sh

  - `deploy.sh` enforces that a Packet Tracer `.deb` exists in repo root.
  - Will fail if containers already exist; use `bash deploy.sh recreate` to clean and redeploy.
  - `start-full-stack.sh` is an alternative script that uses `docker-compose` for core services then launches containers; see `ptweb-vnc/scripts/start-full-stack.sh`.

- Recreate/reset deployment (removes all containers and volumes, then redeploys fresh):

    bash deploy.sh recreate

  Useful when you want a clean slate without manual cleanup commands.

- Add / remove instances at runtime:

    bash add-instance.sh [N]
    bash remove-instance.sh [N|name...]

- Full health test (post-deploy):

    bash test-deployment.sh

  This runs a 41-test healthcheck used by maintainers — useful to reproduce CI failures locally.

## Code patterns & conventions (useful examples)

- Runtime install separation: the `Dockerfile` purposefully does not include the proprietary Packet Tracer `.deb`. Instead, `customizations/runtime-install.sh` and `pt-install.*` handle the installation inside containers. When changing installation behavior, prefer editing `ptweb-vnc/customizations/*`.
- Logging markers: the deployment scripts scan container logs for the Packet Tracer install completion. Look for markers like `\[pt-install\]` or the success message used in scripts (e.g. `✓ SUCCESS: PacketTracer binary ready`). Preserve these markers if you alter install output parsing.
- DB & credentials: scripts assume default DB user/password (`ptdbuser`/`ptdbpass`) and DB name `guacamole_db`. If you change environment names, update `docker-compose.yml`, `deploy.sh`, and `generate-dynamic-connections.sh` together.
- Container resource defaults: containers are started with small CPU/memory defaults (e.g. `--cpus=0.1 -m 512M` in some scripts). Use `tune_ptvnc.sh` to change these across running containers.

## Integration points and files to inspect when editing features

- ptweb-vnc/Dockerfile — base image, packages, user setup
- ptweb-vnc/customizations/* — installer helpers and startup (`start`, `start-session`) used at container runtime
- ptweb-vnc/db-dump.sql — Guacamole DB schema; used by `deploy.sh` and `start-full-stack.sh`
- ptweb-vnc/pt-nginx/ — static UI, nginx config (exposes downloads & guacamole)
- generate-dynamic-connections.sh — how connections are generated for Guacamole (important when changing naming or porting to another remote desktop service)
- test-deployment.sh — canonical behavioural tests and expected outputs to preserve

## Gotchas & pay attention to

- When You run Terminal commands make sure not to redirect the std output. The output needs to be visible in the terminal for debugging and log scanning.

- The Packet Tracer installer is proprietary and must be supplied by the user; CI smoke scripts only test for the presence of the binary path after installation.
- The code expects `/shared` to be present and writable; tests and workflows rely on this mount for file exchange and `pt-nginx/www` for HTTP downloads.
- DB import may fail harmlessly if already applied; scripts commonly `|| true` the import step. If debugging, inspect `guacamole-mariadb` logs and `docker exec` into the container to run SQL manually.
- Try not to redirect the stdout in the commands since the output needs to be visible in the terminal for debugging and log scanning.

## What to update in this file

- If you add new automation scripts, add a short entry under "Available Scripts" in `README.md` and update this file with how agents should run them.
- If you change container or image naming conventions, update the "Architecture notes" section and the scripts listed above.

If anything here is unclear or you'd like the agent to focus more on CI, refactorability, or testing, tell me which area to expand and I'll iterate.
