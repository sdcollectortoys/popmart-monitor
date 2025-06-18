FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install dependencies (no OS deps needed beyond Python)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scripts & strip any stray CRs
COPY monitor.py start.sh ./
RUN sed -i 's/\r$//' start.sh

# We explicitly invoke bash, avoiding reliance on shebang parsing
CMD ["bash", "start.sh"]
