test -x /etc/X11/Xsession && exec /etc/X11/Xsession
#!/bin/bash
# X session startup with PacketTracer auto-launcher
# Supports TurboVNC + VirtualGL when available to enable hardware-accelerated 3D

if test -r /etc/profile; then
    . /etc/profile
fi

# Prefer user's .xinitrc
if [ -f /home/ptuser/.xinitrc ]; then
    exec /home/ptuser/.xinitrc
fi

# If TurboVNC (vncserver) is available, start it and ensure display :1 is present.
if command -v vncserver >/dev/null 2>&1; then
    # Start TurboVNC on display :1 if not already running
    if ! pgrep -f "Xturbovnc|Xvnc" >/dev/null 2>&1; then
        su - ptuser -c "vncserver -geometry 1920x1080 -depth 24 :1" >/dev/null 2>&1 || true
        sleep 1
    fi
fi

# If TurboVNC/VirtualGL are available, create a launcher that uses vglrun.
LAUNCHER=/usr/local/bin/pt-autostart
cat > "$LAUNCHER" << 'PTLAUNCH'
#!/bin/bash
# Run as ptuser; ensure X display and auth are set
export DISPLAY=:1
export XAUTHORITY=/home/ptuser/.Xauthority
export QT_QPA_PLATFORM=xcb
export QT_DEBUG_PLUGINS=0
export LIBGL_ALWAYS_INDIRECT=0
export LIBGL_INDIRECT_DISPATCH=1
export LIBGL_DRIVERS_PATH=/usr/lib/x86_64-linux-gnu/dri
export GALLIUM_DRIVER=llvmpipe
export MESA_GL_VERSION_OVERRIDE=4.6

# Give desktop a moment to start
sleep 5

# If vglrun exists, prefer it to enable GL redirection
if command -v vglrun >/dev/null 2>&1; then
    if [ -x /opt/pt/squashfs-root/AppRun ]; then
        # run PacketTracer under VirtualGL
        vglrun /opt/pt/squashfs-root/AppRun > /tmp/packettracer.log 2>&1 &
    fi
else
    if [ -x /opt/pt/squashfs-root/AppRun ]; then
        /opt/pt/squashfs-root/AppRun > /tmp/packettracer.log 2>&1 &
    fi
fi
PTLAUNCH

chmod 755 "$LAUNCHER"
chown ptuser:ptuser "$LAUNCHER" 2>/dev/null || true

# Execute launcher as the session user
su - ptuser -c "$LAUNCHER" &

# Start desktop environment (fallback)
test -x /etc/X11/Xsession && exec /etc/X11/Xsession
exec /bin/sh /etc/X11/Xsession
