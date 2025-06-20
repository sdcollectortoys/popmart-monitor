FROM python:3.11-slim

# Install Chromium & chromedriver
RUN apt-get update && \
    apt-get install -y chromium chromium-driver && \
    rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_PATH=/usr/bin/chromedriver
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py start.sh ./
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

CMD ["bash", "start.sh"]
