FROM python:3.11-slim

# 1. Install OS-level dependencies for Playwright
RUN apt-get update \
 && apt-get install -y \
    wget gnupg2 curl \
    libnss3 libatk-bridge2.0-0 libcairo2 \
    libx11-xcb1 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libpangocairo-1.0-0 \
    libpango-1.0-0 libasound2 libatspi2.0-0 \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 2. Install Python dependencies (including playwright)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 3. Install Playwright’s Chromium browser

# 4. Copy application code
COPY . .

# 5. Expose health-check port
EXPOSE 10000

# 6. Start your monitor
CMD ["python3", "monitor.py"]
