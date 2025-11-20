FROM ubuntu:22.04
LABEL maintainer="Jozef Janitor"

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime packages including TurboVNC/VirtualGL support
# TurboVNC: High-performance VNC server optimized for 3D rendering
# VirtualGL: GPU-accelerated 3D rendering over network
# libfuse2: Required for AppImage execution (PacketTracer uses AppImage format)
RUN apt-get update && \
    apt-get -y update && apt-get -y install --no-install-recommends \
      util-linux xvfb x11-xserver-utils xauth autocutsel expect sudo xdg-utils dbus-x11 xfce4 \
      dialog gtk-update-icon-cache \
      libpulse0 libnss3 libnspr4 libharfbuzz0b libxss1 libasound2 libxslt1.1 \
      libxcb-xinerama0 libxcb-xinerama0-dev libxcb-cursor0 \
      libxcb-keysyms1 libxcb-xfixes0 libuuid1 libxcb-util1 libxkbcommon0 libxkbcommon-x11-0 \
      libice6 libsm6 libxrender1 libxcb-sync1 libxcb-shape0 libxcb-render0 libxcb-render-util0 libxcb-randr0 libxcb-shm0 libxcb-image0 libxcb-icccm4 libx11-xcb1 \
      libfreetype6 libgl1 libglx-mesa0 \
      libqt6gui6 libqt6widgets6 libqt6core6 libqt6dbus6 libqt6network6 libqt6networkauth6 libqt6webenginecore6 libqt6webenginewidgets6 libqt6qml6 libqt6xml6 libqt6concurrent6 libqt6opengl6 qt6-qpa-plugins \
      libegl1-mesa libgles2-mesa libxinerama1 libxrandr2 libglib2.0-0 libopengl0 \
      libglvnd0 libglvnd-dev libosmesa6 libosmesa6-dev mesa-utils \
      fonts-dejavu-core xfonts-base xfonts-100dpi xfonts-75dpi \
      wget ca-certificates pkg-config libxv1 libxvmc1 libfuse2 \
    && rm -rf /var/lib/apt/lists/*

# Download and install TurboVNC from GitHub release
RUN cd /tmp && \
    echo "Downloading TurboVNC 3.2.1 from GitHub..." && \
    wget -q https://github.com/TurboVNC/turbovnc/releases/download/3.2.1/turbovnc_3.2.1_amd64.deb && \
    echo "Installing TurboVNC..." && \
    dpkg -i turbovnc_3.2.1_amd64.deb && \
    rm -f turbovnc_3.2.1_amd64.deb && \
    echo "✓ TurboVNC 3.2.1 installed successfully" && \
    /opt/TurboVNC/bin/vncserver --version 2>&1 | head -1

# Download and install VirtualGL from GitHub release
RUN cd /tmp && \
    echo "Downloading VirtualGL 3.1.1 from GitHub..." && \
    wget -q https://github.com/VirtualGL/virtualgl/releases/download/3.1.1/virtualgl_3.1.1_amd64.deb && \
    echo "Installing VirtualGL..." && \
    dpkg -i virtualgl_3.1.1_amd64.deb && \
    rm -f virtualgl_3.1.1_amd64.deb && \
    /usr/bin/vglserver_config +s +f >/dev/null 2>&1 || true && \
    echo "✓ VirtualGL 3.1.1 installed successfully with GPU support configured" && \
    vglrun --version 2>&1 | head -1

WORKDIR /

RUN useradd -m -s /bin/bash ptuser

COPY customizations/ /

# Copy PacketTracer .deb if it exists (deploy.sh copies it with this exact name)
# Using ADD allows us to gracefully skip if file doesn't exist
ADD CiscoPacketTracer.deb /CiscoPacketTracer.deb

RUN chmod +x /start /start-session /pt-install.xp
# Ensure xstartup and installer helper are executable
RUN chmod +x /home/ptuser/.vnc/xstartup /pt-install.sh || true
# Remove autostart to prevent multiple Packet Tracer instances
# Users can still launch via taskbar icon or manually
RUN rm -f /home/ptuser/.config/autostart/PacketTracer.desktop || true

# Copy helper scripts (runtime installer and detector)
COPY customizations/runtime-install.sh /runtime-install.sh
RUN chmod +x /runtime-install.sh || true
COPY customizations/pt-detect.sh /pt-detect.sh
RUN chmod +x /pt-detect.sh && /pt-detect.sh || true

# PacketTracer .deb installation (optional, should be in build context if deploy.sh provided it)
# Using apt install which handles pre/post install scripts and EULA automatically with DEBIAN_FRONTEND=noninteractive
RUN if ls /CiscoPacketTracer.deb 1>/dev/null 2>&1; then \
      PT_DEB=$(ls /CiscoPacketTracer.deb | head -1); \
      echo "[pt-install] Found PacketTracer .deb: $PT_DEB - installing with apt..."; \
      export DEBIAN_FRONTEND=noninteractive && \
      apt-get update && \
      apt-get install -y "$PT_DEB" && \
      rm -f "$PT_DEB" && \
      if [ -f /opt/pt/packettracer.AppImage ] || [ -x /opt/pt/packettracer ]; then \
        echo "[pt-install] ✓ SUCCESS: PacketTracer installed successfully"; \
        echo "[pt-install] PacketTracer location: $(ls -lh /opt/pt/packettracer* 2>/dev/null | head -1)"; \
      fi; \
    else \
      echo "[pt-install] No PacketTracer .deb found in build context, skipping installation"; \
    fi || true

RUN rm -f /PacketTracer* /PacketTracer_* /PacketTracer-*_amd64.deb || true
# Remove any committed VNC passwd file so start-session generates one at runtime
RUN rm -f /home/ptuser/.vnc/passwd || true

RUN apt-get clean -y

RUN chown -R ptuser /home/ptuser

# Create /opt/pt directory for Packet Tracer installation (if not already created by .deb)
RUN mkdir -p /opt/pt && chmod 755 /opt/pt

# Create wrapper script for PacketTracer that handles both AppImage and regular binary
RUN mkdir -p /opt/pt && \
    echo '#!/bin/bash' > /opt/pt/packettracer-launcher && \
    echo 'if [ -x /opt/pt/packettracer.AppImage ]; then' >> /opt/pt/packettracer-launcher && \
    echo '  cd /tmp' >> /opt/pt/packettracer-launcher && \
    echo '  /opt/pt/packettracer.AppImage --appimage-extract >/dev/null 2>&1' >> /opt/pt/packettracer-launcher && \
    echo '  exec ./squashfs-root/AppRun "$@"' >> /opt/pt/packettracer-launcher && \
    echo 'elif [ -x /opt/pt/bin/PacketTracer ]; then' >> /opt/pt/packettracer-launcher && \
    echo '  exec /opt/pt/bin/PacketTracer "$@"' >> /opt/pt/packettracer-launcher && \
    echo 'elif [ -x /opt/pt/packettracer ]; then' >> /opt/pt/packettracer-launcher && \
    echo '  exec /opt/pt/packettracer "$@"' >> /opt/pt/packettracer-launcher && \
    echo 'else' >> /opt/pt/packettracer-launcher && \
    echo '  echo "Error: PacketTracer not found at any known location"' >> /opt/pt/packettracer-launcher && \
    echo '  exit 1' >> /opt/pt/packettracer-launcher && \
    echo 'fi' >> /opt/pt/packettracer-launcher && \
    chmod +x /opt/pt/packettracer-launcher

# Create desktop shortcut for Packet Tracer
RUN mkdir -p /home/ptuser/Desktop && \
    echo '[Desktop Entry]' > /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Version=1.0' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Type=Application' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Name=Packet Tracer' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Comment=Network Simulator' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Exec=/opt/pt/packettracer-launcher %f' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Icon=/opt/pt/art/app.png' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Path=/opt/pt' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Terminal=false' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'StartupNotify=true' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    echo 'Categories=Education;Science;' >> /home/ptuser/Desktop/PacketTracer.desktop && \
    chmod +x /home/ptuser/Desktop/PacketTracer.desktop && \
    chown ptuser:ptuser /home/ptuser/Desktop/PacketTracer.desktop

ENTRYPOINT ["/start"]


