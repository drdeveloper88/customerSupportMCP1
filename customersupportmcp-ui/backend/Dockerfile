# ── CustomerSupportMCP — FastAPI Backend ──────────────────────────────────────
# Multi-stage build: slim final image.
# Bundles the MCP server code so the backend can spawn it via
# PythonStdioTransport (MCP_SERVER_PATH points to /app/mcp_server/main.py).
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim AS base

# Security: non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# ── Install Python dependencies ───────────────────────────────────────────────
# Install backend deps first (cached layer)
COPY customersupportmcp-ui/backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install MCP server deps (backend imports MCP modules directly via sys.path)
# Includes chromadb, sentence-transformers, langchain, langgraph, etc.
COPY customersupportmcp/requirements.txt ./mcp_requirements.txt
RUN pip install --no-cache-dir -r mcp_requirements.txt

# ── Copy backend source ──────────────────────────────────────────────
COPY customersupportmcp-ui/backend/ .

# ── Bundle MCP server alongside the backend ───────────────────────────────
# At runtime the backend adds /app/mcp_server to sys.path and imports directly.
COPY customersupportmcp/ ./mcp_server/

# Create logs directory
RUN mkdir -p logs && chown -R appuser:appgroup /app

USER appuser

# ── Environment defaults ──────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1 \
    LOG_LEVEL=INFO \
    LOG_FORMAT=json \
    MCP_SERVER_PATH=/app/mcp_server/main.py \
    PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
