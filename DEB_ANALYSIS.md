# PacketTracer .deb Analysis - November 2025 Release

## Version Information
- **Version**: 9.0.0 (from packettracer wrapper script)
- **Release Date**: February 13, 2025
- **Package Size**: ~300MB

## Key Installation Structure

### Binary Locations (CRITICAL)
The package contains TWO executable paths:
1. **`/opt/pt/packettracer`** - Bash wrapper script (181 bytes)
2. **`/opt/pt/bin/PacketTracer`** - Main executable binary (107MB)

### The Wrapper Script (`/opt/pt/packettracer`)
```bash
#!/bin/bash
echo Starting Packet Tracer 9.0.0
PTDIR=/opt/pt
export LD_LIBRARY_PATH=/opt/pt/bin
pushd /opt/pt/bin > /dev/null
./PacketTracer "$@" > /dev/null 2>&1
popd > /dev/null
```

**Key Points:**
- Sets `LD_LIBRARY_PATH` to `/opt/pt/bin` (required for library dependencies)
- Changes to `/opt/pt/bin` directory before execution
- Suppresses all output (redirects to /dev/null)
- Designed for GUI launch (not headless)

### Directory Structure
```
/opt/pt/
├── bin/PacketTracer          (107MB executable)
├── bin/Linux/                (libraries)
├── bin/audio/                (Qt audio plugins)
├── bin/imageformats/         (Qt image plugins)
├── bin/mediaservice/         (Qt media plugins)
├── bin/platforms/            (Qt platform plugins)
├── bin/sqldrivers/           (Qt SQL drivers)
├── bin/tls/                  (SSL/TLS support)
├── bin/xcbglintegrations/    (X11 OpenGL support)
├── packettracer              (wrapper script - symlinked to /usr/local/bin)
├── linguist                  (translator tool)
├── art/                      (graphics assets)
├── backgrounds/              (UI backgrounds)
├── extensions/               (plugin extensions)
├── font/                     (custom fonts)
├── help/                     (documentation)
├── languages/                (language files)
├── plugins/                  (plugin directory)
├── Sounds/                   (audio files)
├── templates/                (network templates)
└── translations/             (Qt translations - .qm files)
```

### Key Dependencies
- Qt6 (Core, Gui, DBus, Multimedia, WebSockets, WebEngine, Serial, 5Compat)
- OpenSSL 3 (libcrypto.so.3)
- Unicode support (icudtl.dat - 11MB)
- Linux kernel modules support

### Post-Installation Actions
The `postinst` script performs:
1. Creates symlink: `/usr/local/bin/packettracer` → `/opt/pt/packettracer`
2. Sets SUID bit on `/opt/pt/bin/updatepttp` for privileged updates
3. Configures environment: Sets `PT8HOME` and `export PT8HOME` in `/etc/profile`
4. Installs icon handlers via `ubuntu-pt-icons.sh`

### Important System Configuration
After installation, the system profile (`/etc/profile`) gets updated with:
```bash
PT8HOME=/opt/pt
export PT8HOME
```

This is used by PacketTracer for configuration and home directory access.

## Changes from Previous Versions

### What's NEW in 9.0.0:
1. **Qt6 Migration**: Now uses Qt6 (not Qt5) - requires newer system libraries
2. **Binary Size**: 107MB (slightly larger)
3. **Stricter Structure**: Binary layout is more rigid in `/opt/pt/bin/`
4. **OpenSSL 3**: Uses libcrypto.so.3 (instead of older 1.1)

### Container Compatibility Notes
- Requires Qt6 runtime libraries in Docker image
- `/opt/pt/bin/LD_LIBRARY_PATH` must be set for runtime
- X11/Wayland support required for GUI
- Headless operation may fail due to GUI assumptions

## Detection Strategy

### Reliable Detection Methods:

1. **Fastest**: Check wrapper script
   ```bash
   test -x /opt/pt/packettracer && echo "Found"
   ```

2. **Binary Direct**: Check main executable
   ```bash
   test -x /opt/pt/bin/PacketTracer && echo "Found"
   ```

3. **Fallback Search**: Use find if paths change
   ```bash
   find /opt/pt -maxdepth 2 -name "PacketTracer" -o -name "packettracer"
   ```

4. **Version Check**: Extract version from wrapper
   ```bash
   grep "Packet Tracer" /opt/pt/packettracer | grep -oP '\d+\.\d+\.\d+'
   ```

## Extraction Details

| File | Size | Purpose |
|------|------|---------|
| data.tar.xz | 300MB | Installation files (data) |
| control.tar.xz | 1.8KB | Control scripts (postinst, postrm, preinst) |
| debian-binary | 4 bytes | Version indicator (always "2.0") |
| _gpgorigin | 543 bytes | GPG signature info |

## Critical Installation Requirements

### For Docker/Container Deployment:
1. Base image must support X11 libraries (even for headless)
2. Set `PT8HOME` environment variable before launch
3. Ensure `/opt/pt/bin` is in `LD_LIBRARY_PATH`
4. Qt6 runtime libraries required
5. OpenSSL 3 (libcrypto.so.3) required

### Verify Installation:
```bash
# Check extraction
test -x /opt/pt/packettracer && \
test -x /opt/pt/bin/PacketTracer && \
echo "✓ Installation successful"

# Check runtime access
/opt/pt/packettracer --help
```

## Updated Detection Script (pt-install.sh)

Based on this analysis, the script should:
1. ✅ Check `/opt/pt/packettracer` (primary)
2. ✅ Check `/opt/pt/bin/PacketTracer` (fallback)
3. ✅ Validate file is executable
4. ✅ Show actual directory listing on failure
5. ✅ Log version from wrapper script

---

**Generated**: November 11, 2025
**Analyzed Package**: CiscoPacketTracer.deb (9.0.0)
