FROM python:3.11-slim

# Install Chrome and its dependencies
RUN apt-get update \
    && apt-get install -y wget gnupg2 unzip \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub \
       | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
       fonts-liberation libappindicator3-1 libasound2 libatk-bridge2.0-0 \
       libcairo2 libdbus-1-3 libdrm2 libgtk-3-0 libnspr4 libnss3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (Selenium Manager will auto-download Chromedriver)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose health-check port
EXPOSE 10000

# Default command
CMD ["./start.sh"]
