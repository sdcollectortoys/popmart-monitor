FROM python:3.11-slim

# install Chrome and dependencies
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

# install chromedriver matching Chrome
RUN CHROME_VERSION=$(google-chrome --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1) \
    && wget -q "https://chromedriver.storage.googleapis.com/${CHROME_VERSION}/chromedriver_linux64.zip" \
       -O /tmp/chromedriver.zip \
    && unzip /tmp/chromedriver.zip -d /usr/local/bin/ \
    && rm /tmp/chromedriver.zip \
    && chmod +x /usr/local/bin/chromedriver

# app setup
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# expose health-check port
EXPOSE 10000

# entrypoint
CMD ["./start.sh"]
