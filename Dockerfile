# Dockerfile
FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# install any needed OS packages (we use sed to strip CRLF)
RUN apt-get update && \
    apt-get install -y wget gnupg2 unzip && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY monitor.py start.sh ./
# remove any Windows CRLFs and ensure executable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

CMD ["./start.sh"]
