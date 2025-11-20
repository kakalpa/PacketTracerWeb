#!/bin/bash
# X session initialization with PacketTracer GL-optimized rendering
# Launches desktop and PacketTracer with proper OpenGL environment

# Wait a moment for X to stabilize
sleep 2

# Launch PacketTracer in background with 5 second delay
# Using GL-optimized environment variables
if [ -f /usr/local/bin/start-packettracer-gl ]; then
  (
    sleep 5
    /usr/local/bin/start-packettracer-gl &
  ) &
elif [ -x /opt/pt/squashfs-root/AppRun ]; then
  (
    sleep 5
    DISPLAY=:1 XAUTHORITY=/home/ptuser/.Xauthority \
    LIBGL_ALWAYS_INDIRECT=0 LIBGL_INDIRECT_DISPATCH=1 \
    GALLIUM_DRIVER=llvmpipe MESA_GL_VERSION_OVERRIDE=4.6 \
    nohup /opt/pt/squashfs-root/AppRun > /tmp/packettracer.log 2>&1 &
  ) &
fi

# Start desktop environment (this blocks and keeps session alive)
exec startxfce4
