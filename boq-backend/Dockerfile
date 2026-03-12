# Almabani BOQ Management System - Docker Image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Set working directory
WORKDIR /app

# Install system dependencies
# Skipped to speed up build - restore if wheels allow
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#     curl \
#     && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install gunicorn for production (optional for worker but kept)
RUN pip install --no-cache-dir gunicorn

# Copy application code
COPY almabani/ ./almabani/
COPY pyproject.toml setup.py ./
COPY worker.py ./

# Install the package
RUN pip install --no-cache-dir -e .

# Create data directories
RUN mkdir -p /app/data/logs

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser \
    && chown -R appuser:appuser /app
USER appuser

# No port exposure for batch worker
# EXPOSE 8080

# No healthcheck for batch worker
# HEALTHCHECK ...

# Default CMD
CMD ["python", "worker.py"]
