#!/bin/bash
set -e

# 1. Start Xvfb (The virtual screen)
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1280x800x24 &
export DISPLAY=:99

# 2. Start a simple window manager (so Chrome has a border/title)
echo "Starting Fluxbox..."
fluxbox &

# 3. Start x11vnc (the bridge from X11 to VNC)
echo "Starting VNC server..."
x11vnc -display :99 -forever -shared -nopw -bg -listen localhost -xkb

# 4. Start websockify (VNC to WebSockets for noVNC)
echo "Starting websockify..."
/opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 8080 &

# 5. Start Nginx
echo "Starting Nginx..."
service nginx start

# 6. Start the Python Backend (Music Studio)
echo "Starting Music Studio..."
# We use fixed port 4173 because Nginx proxies to it
export PORT=4173
python main.py
