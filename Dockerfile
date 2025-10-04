# Use Python 3.12 slim image
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies including uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    sqlite3 \
    curl && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    rm -rf /var/lib/apt/lists/*

# Copy pyproject.toml
COPY pyproject.toml .

# Install Python dependencies using uv
RUN /root/.cargo/bin/uv pip install --system flask pillow

# Copy application files
COPY app.py .
COPY templates/ templates/

# Create directory for database
RUN mkdir -p /data

# Set environment variables
ENV FLASK_APP=app.py
ENV DATABASE=/data/anika_blue.db
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/').read()" || exit 1

# Run the application
CMD ["python", "app.py"]
