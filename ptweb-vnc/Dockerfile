FROM ubuntu:20.04
LABEL maintainer="Jozef Janitor"

ENV DEBIAN_FRONTEND=noninteractive

# Install runtime packages only (no dev tools) and clean apt lists in one layer
RUN apt-get update && \
    apt-get -y update && apt-get -y install --no-install-recommends \
      util-linux tightvncserver autocutsel expect sudo xdg-utils dbus-x11 xfce4 \
      libpulse0 libnss3 libnspr4 libharfbuzz0b libxss1 libasound2 libxslt1.1 \
      dialog libxcb-xinerama0 libxcb-xinerama0-dev \
      libxcb-keysyms1 libxcb-xfixes0 libuuid1 libxcb-util1 libxkbcommon0 libxkbcommon-x11-0 \
      libice6 libsm6 libxrender1 libxcb-sync1 libxcb-shape0 libxcb-render0 libxcb-render-util0 libxcb-randr0 libxcb-shm0 libxcb-image0 libxcb-icccm4 libx11-xcb1 \
      libqt5gui5 libqt5widgets5 libqt5core5a libqt5dbus5 libqt5network5 libqt5webenginecore5 libqt5webenginewidgets5 \
      libgl1-mesa-glx libegl1-mesa libgles2-mesa libxinerama1 libxrandr2 libglib2.0-0 \
        fonts-dejavu-core xfonts-base xfonts-100dpi xfonts-75dpi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /

RUN adduser --disabled-password --gecos "" ptuser

COPY customizations/ /
RUN chmod +x /start /start-session /pt-install.xp

COPY *.deb /
RUN /pt-install.xp || true
COPY customizations/pt-detect.sh /pt-detect.sh
RUN chmod +x /pt-detect.sh && /pt-detect.sh || true
RUN rm -f /PacketTracer* /PacketTracer_* /PacketTracer-*_amd64.deb || true
# Remove any committed VNC passwd file so start-session generates one at runtime
RUN rm -f /home/ptuser/.vnc/passwd || true

RUN apt-get clean -y

RUN chown -R ptuser /home/ptuser

ENTRYPOINT ["/start"]


