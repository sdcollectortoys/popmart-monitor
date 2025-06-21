FROM python:3.11-slim

WORKDIR /app

# install only our Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy the script and launcher
COPY monitor.py start.sh ./
RUN chmod +x start.sh

# health-check port
EXPOSE 8000

# kick off
CMD ["./start.sh"]
