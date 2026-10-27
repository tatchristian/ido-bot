# Multi-stage or slim Python image for IDO Tournament Bot
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY . .

# Create non-root user and persistent data directory
RUN useradd -u 1000 -m -s /bin/bash appuser && \
    mkdir -p /app/data /app/data/backups && \
    chown -R appuser:appuser /app

USER appuser

# Expose volume for atomic JSON storage and backups
VOLUME ["/app/data"]

CMD ["python", "bot.py"]
