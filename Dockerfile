# Dockerfile
FROM python:3.11-slim

# Install Chromium & chromedriver
RUN apt-get update && \
    apt-get install -y chromium chromium-driver && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY monitor.py start.sh ./

# Normalize line endings and make start.sh executable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Use bash to launch
CMD ["bash", "start.sh"]
