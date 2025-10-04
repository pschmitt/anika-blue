# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies including uv
# hadolint ignore=DL3008
RUN apt-get update && \
    apt-get install -y --no-install-recommends sqlite3 && \
    mkdir -p /app /data && \
    rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app

RUN pip install --no-cache-dir /app

# Set environment variables
ENV DATABASE=/data/anika_blue.db
ENV BIND_HOST=0.0.0.0
ENV BIND_PORT=5000
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/').read()" || exit 1

# Run the application
CMD ["anika-blue"]
