This project was updated to support Ubuntu 20.04 and Packet Tracer 8.x+.

Summary of changes
- Dockerfile base image updated from `ubuntu:18.04` to `ubuntu:20.04`.
- Qt4 packages removed; Qt5 and modern graphics libs added (libqt5gui5, libqt5widgets5, qt5-default, libgl1-mesa-glx, etc.).
- `customizations/pt-install.xp` updated to accept a wider set of PacketTracer .deb filename patterns (v7 and v8+).
- Added `customizations/pt-detect.sh` to create a consistent `/opt/pt/packettracer` symlink pointing to the installed binary name.
- `customizations/start-session` updated to detect Packet Tracer process names used by PT 8.x (PacketTracer, packettracer).
- Desktop .desktop files updated to generic "Packet Tracer" name (no longer hardcoded to 7.3.0).
- Dockerfile now runs the detect script after installation and only removes PacketTracer .deb files.

How to use
1. Place the Packet Tracer .deb(s) into the repository root before building the image. Example filenames supported:
   - `PacketTracer_731_amd64.deb` (older style)
   - `PacketTracer-8.0.0-xxxx_amd64.deb` (v8 style)
   - `PacketTracer8_...amd64.deb`

2. Build the Docker image (from the repo root):

```bash
# from repo root
docker build -t ptweb-vnc .
```

Notes and known caveats
- Packet Tracer is a proprietary application; the .deb must be provided by the user.
- PT 8.x may require additional libraries depending on the exact build/distribution from Cisco. If you see missing library errors at runtime, install the named libs into the Dockerfile or host.
- The image now targets Ubuntu 20.04; if you need to remain on 18.04 for other reasons, revert the base image and Qt5 changes.

Troubleshooting
- If Packet Tracer fails to start inside the container, check the VNC logs in `/home/ptuser/.vnc/` and run `ls -l /opt/pt` inside the container to see binary names.
- To manually create the symlink inside a running container:

```bash
# inside container as root
if [ -x /opt/pt/packettracer ]; then echo ok; else \
  for b in /opt/pt/PacketTracer* /opt/pt/packettracer /opt/pt/PacketTracer7.* /opt/pt/packettracer8*; do \
    [ -x "$b" ] && ln -sfn "$b" /opt/pt/packettracer && break; \
  done; fi
```

Next steps (optional)
- Add minimal automated smoke tests that build the image and run the container to verify PT binary exists.
- If you want to support multiple Ubuntu targets, parameterize the Dockerfile via build-arg.

CI
--
This repository now includes a GitHub Actions workflow at `.github/workflows/ci.yml` which will:
- Fail early if no PacketTracer .deb is present in the repository root.
- Build the Docker image and run a smoke check to ensure `/opt/pt/packettracer` exists inside the image.

You can also run the local smoke script:

```bash
chmod +x scripts/ci-smoke.sh
./scripts/ci-smoke.sh
```

