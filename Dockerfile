# Use a stable Python image
FROM python:3.11-slim

# Install system dependencies for Chrome, FFmpeg, and VNC
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    xvfb \
    fluxbox \
    x11vnc \
    git \
    net-tools \
    novnc \
    python3-websockify \
    ffmpeg \
    nginx \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Install Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Set up noVNC
RUN mkdir -p /opt/novnc && \
    ln -s /usr/share/novnc/* /opt/novnc/ && \
    cp /usr/share/novnc/vnc.html /usr/share/novnc/index.html

# Set working directory
WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Nginx config
COPY nginx.conf /etc/nginx/sites-available/default

# Copy the rest of the application
COPY . .

# Make scripts executable
RUN chmod +x entrypoint.sh

# Environment variables
ENV DISPLAY=:99
ENV PYTHONUNBUFFERED=1
ENV NO_OPEN_BROWSER=1

# The app runs on 4173 internally, Nginx exposes 80 (standard for Render)
EXPOSE 80

# Start everything via entrypoint
ENTRYPOINT ["./entrypoint.sh"]
