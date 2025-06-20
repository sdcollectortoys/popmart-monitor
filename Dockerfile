FROM python:3.11-slim

# Ensure Python output is unbuffered
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install HTTP + HTML parsing deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy your monitor and startup script
COPY monitor.py start.sh ./

# Normalize line endings and make start.sh executable
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh

# Launch the monitor loop
CMD ["bash", "start.sh"]
