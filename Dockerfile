FROM python:3.11-slim

# install Chrome & chromedriver
RUN apt-get update && \
    apt-get install -y wget gnupg2 unzip && \
    # install Google Chrome
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - && \
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" \
      > /etc/apt/sources.list.d/google-chrome.list && \
    apt-get update && \
    apt-get install -y google-chrome-stable && \
    # install chromedriver matching Chrome version
    CHROME_VER=$(google-chrome --version | awk '{print $3}' | cut -d. -f1) && \
    wget -q "https://chromedriver.storage.googleapis.com/${CHROME_VER}.0/chromedriver_linux64.zip" && \
    unzip chromedriver_linux64.zip && mv chromedriver /usr/local/bin/ && chmod +x /usr/local/bin/chromedriver && \
    rm chromedriver_linux64.zip && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# env vars for Selenium
ENV CHROME_BIN=/usr/bin/google-chrome-stable
ENV CHROMEDRIVER_PATH=/usr/local/bin/chromedriver
ENV PYTHONUNBUFFERED=1

# copy and install requirements
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy your scripts
COPY monitor.py start.sh ./
RUN chmod +x start.sh

CMD ["./start.sh"]
