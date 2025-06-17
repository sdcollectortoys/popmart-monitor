# Dockerfile
FROM python:3.11-slim

# Install Chromium & Chromedriver from Debian repos
RUN apt-get update && \
    apt-get install -y \
      wget \
      gnupg2 \
      unzip \
      chromium \
      chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Point Selenium at the right binaries
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1

# App setup
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py start.sh ./
RUN chmod +x start.sh

CMD ["./start.sh"]
