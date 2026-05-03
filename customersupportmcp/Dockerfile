# ── CustomerSupportMCP — MCP Server ──────────────────────────────────────────
# Runs as a child process spawned by the backend via PythonStdioTransport.
# The backend container mounts / copies this code and sets MCP_SERVER_PATH.
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Security: non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Install dependencies separately so layer is cached on code changes
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Create logs directory (owned by appuser)
RUN mkdir -p logs && chown -R appuser:appgroup /app

USER appuser

# Environment defaults (override via docker-compose / K8s env)
ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json

# The MCP server is normally spawned over stdio by the backend.
# Providing a default CMD makes the image independently runnable for testing.
CMD ["python", "main.py"]
