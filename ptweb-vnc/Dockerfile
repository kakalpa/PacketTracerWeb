FROM ubuntu:22.04
LABEL maintainer="Jozef Janitor"

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime packages only (no dev tools) and clean apt lists in one layer
RUN apt-get update && \
    apt-get -y update && apt-get -y install --no-install-recommends \
      util-linux tightvncserver autocutsel expect sudo xdg-utils dbus-x11 xfce4 \
      dialog gtk-update-icon-cache \
      libpulse0 libnss3 libnspr4 libharfbuzz0b libxss1 libasound2 libxslt1.1 \
      libxcb-xinerama0 libxcb-xinerama0-dev libxcb-cursor0 \
      libxcb-keysyms1 libxcb-xfixes0 libuuid1 libxcb-util1 libxkbcommon0 libxkbcommon-x11-0 \
      libice6 libsm6 libxrender1 libxcb-sync1 libxcb-shape0 libxcb-render0 libxcb-render-util0 libxcb-randr0 libxcb-shm0 libxcb-image0 libxcb-icccm4 libx11-xcb1 \
      libfreetype6 libgl1 libglx-mesa0 \
      libqt6gui6 libqt6widgets6 libqt6core6 libqt6dbus6 libqt6network6 libqt6networkauth6 libqt6webenginecore6 libqt6webenginewidgets6 libqt6qml6 libqt6xml6 libqt6concurrent6 libqt6opengl6 qt6-qpa-plugins \
      libegl1-mesa libgles2-mesa libxinerama1 libxrandr2 libglib2.0-0 libopengl0 \
        fonts-dejavu-core xfonts-base xfonts-100dpi xfonts-75dpi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

RUN useradd -m -s /bin/bash ptuser

COPY customizations/ /
RUN chmod +x /start /start-session /pt-install.xp
# Ensure xstartup and installer helper are executable
RUN chmod +x /home/ptuser/.vnc/xstartup /pt-install.sh || true
# Remove autostart to prevent multiple Packet Tracer instances
# Users can still launch via taskbar icon or manually
RUN rm -f /home/ptuser/.config/autostart/PacketTracer.desktop || true

# Do NOT copy PacketTracer .deb into the image. Installers are proprietary and
COPY customizations/runtime-install.sh /runtime-install.sh
RUN chmod +x /runtime-install.sh || true
COPY customizations/pt-detect.sh /pt-detect.sh
RUN chmod +x /pt-detect.sh && /pt-detect.sh || true
RUN rm -f /PacketTracer* /PacketTracer_* /PacketTracer-*_amd64.deb || true
# Remove any committed VNC passwd file so start-session generates one at runtime
RUN rm -f /home/ptuser/.vnc/passwd || true

RUN apt-get clean -y

RUN chown -R ptuser /home/ptuser

# Create /opt/pt directory for Packet Tracer installation
RUN mkdir -p /opt/pt && chmod 755 /opt/pt

ENTRYPOINT ["/start"]


