#!/bin/bash
set -e

# 1. Start Xvfb (The virtual screen)
echo "Starting Xvfb..."
Xvfb :99 -screen 0 1280x800x24 -ac &
export DISPLAY=:99

# Wait for Xvfb to be ready
sleep 2

# 2. Start Fluxbox
echo "Starting Fluxbox..."
fluxbox &

# 3. Start x11vnc in a resilient background loop to survive slow Xvfb startups
echo "Starting VNC server..."
x11vnc -display :99 -forever -shared -nopw -loop &

# 4. Start websockify (VNC to WebSockets)
echo "Starting websockify..."
/opt/novnc/utils/novnc_proxy --vnc localhost:5900 --listen 8080 &

# 5. Start the Python Backend in the background
echo "Starting Music Studio..."
export PORT=4173
python main.py &

# 6. Start Nginx in the FOREGROUND (keeps the container alive)
echo "Starting Nginx..."
nginx -g 'daemon off;'
