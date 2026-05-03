"""
Centralised application configuration loaded from .env.

Using plain os.getenv (no Pydantic dependency) to keep the requirements
lean.  All public names follow UPPER_SNAKE_CASE (PEP 8 module constants).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_PATH)

# ── MCP server ────────────────────────────────────────────────────────────────

MCP_SERVER_PATH: str = os.environ.get(
    "MCP_SERVER_PATH",
    str(
        Path(__file__).resolve().parent.parent.parent.parent
        / "customersupportmcp"
        / "main.py"
    ),
)

# ── CORS / Security ───────────────────────────────────────────────────────────

FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173")
ALLOWED_ORIGINS: list[str] = [
    FRONTEND_URL,
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

# ── Server ────────────────────────────────────────────────────────────────────

API_VERSION: str = "v1"
APP_TITLE: str = "Customer Support MCP API"
APP_DESCRIPTION: str = (
    "REST + WebSocket backend that bridges the React UI to the "
    "CustomerSupportMCP FastMCP server."
)
APP_VERSION: str = "1.0.0"

# ── Observability ─────────────────────────────────────────────────────────────

LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()

# ── Rate limiting (requests per minute per IP) ────────────────────────────────

RATE_LIMIT_CHAT: str = os.getenv("RATE_LIMIT_CHAT", "30/minute")
RATE_LIMIT_API: str = os.getenv("RATE_LIMIT_API", "60/minute")
