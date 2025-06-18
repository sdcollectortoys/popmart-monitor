# Dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py start.sh ./
RUN chmod +x start.sh

CMD ["./start.sh"]
