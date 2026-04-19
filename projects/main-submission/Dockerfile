FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install runtime deps first (better layer cache)
COPY pyproject.toml ./
RUN pip install --no-cache-dir \
      "openai>=1.0.0" \
      "fastmcp>=0.1.0" \
      "fastapi>=0.110.0" \
      "uvicorn>=0.27.0" \
      "httpx>=0.27.0"

# Copy source
COPY src ./src
COPY scripts ./scripts
COPY runtime/fixtures ./runtime/fixtures

# Create runtime dirs
RUN mkdir -p /app/runtime/local_mirror

ENV PYTHONPATH=/app/src \
    COPILOT_DB_PATH=/app/runtime/incidents.db \
    COPILOT_HOST=0.0.0.0 \
    COPILOT_PORT=8080

EXPOSE 8080

# Healthcheck — the /health endpoint always returns 200 when the app is up
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://localhost:8080/health', timeout=2)" || exit 1

CMD ["python", "scripts/run_server.py"]
