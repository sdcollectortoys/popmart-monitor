# Dockerfile
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install only what we need
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy our scripts
COPY monitor.py start.sh ./
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

CMD ["bash", "start.sh"]
