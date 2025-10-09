FROM ubuntu:20.04

ENV DEBIAN_FRONTEND=noninteractive

# --- Base dependencies ---
RUN apt-get update && \
    apt-get -y install tightvncserver autocutsel expect sudo \
    xfce4 tango-icon-theme dbus-x11 firejail && \
    apt-get -y remove xscreensaver && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Packet Tracer dependencies ---
RUN apt-get update && apt-get -y install \
    xdg-utils gtk-update-icon-cache dialog \
    libgl1-mesa-glx libpulse0 libnss3 libxss1 libasound2 \
    libxslt1.1 libxkbcommon-x11-0 libxcb-xinerama0-dev \
    libfreetype6 libstdc++6 libfontconfig1 \
    libqt5core5a libqt5gui5 libqt5widgets5 libqt5network5 \
    libqt5dbus5 libqt5xml5 libqt5xmlpatterns5 \
    qtbase5-dev-tools qml-module-qtquick-controls qtchooser \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# --- Add ptuser ---
RUN adduser --disabled-password --gecos "" ptuser

# --- Copy scripts ---
COPY customizations/ /
RUN chmod +x /start /start-session /pt-install.xp

# --- Copy and install Packet Tracer ---
COPY *.deb /
RUN /pt-install.xp && rm /*.deb

# --- Fix permissions ---
RUN chown -R ptuser /home/ptuser
RUN ls -a /
# --- Firejail sandbox config ---
RUN echo "net=none" > /etc/firejail/packettracer.profile && \
    echo "noblacklist ${HOME}" >> /etc/firejail/packettracer.profile && \
    echo "private" >> /etc/firejail/packettracer.profile && \
    echo "noroot" >> /etc/firejail/packettracer.profile

USER ptuser
WORKDIR /home/ptuser

ENTRYPOINT ["/start"]

