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

FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:3000")
ALLOWED_ORIGINS: list[str] = [
    FRONTEND_URL,
    "http://localhost:3000",
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
RATE_LIMIT_AUTH: str = os.getenv("RATE_LIMIT_AUTH", "5/minute")       # login / register
RATE_LIMIT_RESET: str = os.getenv("RATE_LIMIT_RESET", "3/minute")     # forgot-password

# ── JWT Authentication ────────────────────────────────────────────────────────
# SECURITY: override JWT_SECRET_KEY in production via environment variable.
# Minimum 32 random characters.
# Generate with: python -c "import secrets; print(secrets.token_hex(32))"

JWT_SECRET_KEY: str = os.getenv(
    "JWT_SECRET_KEY",
    "change-me-in-production-use-a-32-char-random-secret",
)
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))  # 8 hours

# ── PostgreSQL ────────────────────────────────────────────────────────────────

DATABASE_URL: str = os.getenv(
    "DATABASE_URL",
    "postgresql://support:changeme@localhost:5432/support",
)

# ── Redis ─────────────────────────────────────────────────────────────────────

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── Password reset ────────────────────────────────────────────────────────────

RESET_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("RESET_TOKEN_EXPIRE_MINUTES", "30"))
EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES", "1440"))  # 24 hours

# ── OAuth2 — Google ───────────────────────────────────────────────────────────
# Register at https://console.cloud.google.com → APIs & Services → Credentials

GOOGLE_CLIENT_ID: str = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET: str = os.getenv("GOOGLE_CLIENT_SECRET", "")

# ── OAuth2 — Facebook ─────────────────────────────────────────────────────────
# Register at https://developers.facebook.com → My Apps → Add a New App

FACEBOOK_APP_ID: str = os.getenv("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET: str = os.getenv("FACEBOOK_APP_SECRET", "")

# Base URL of this API server (used to build OAuth callback URLs).
# In Docker Compose this is the externally accessible backend URL.
OAUTH_REDIRECT_BASE_URL: str = os.getenv(
    "OAUTH_REDIRECT_BASE_URL", "http://localhost:8000"
)

# ── Email (SMTP) ──────────────────────────────────────────────────────────────
# Leave SMTP_HOST empty to use console-log mode in development.

SMTP_HOST: str = os.getenv("SMTP_HOST", "")
SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER: str = os.getenv("SMTP_USER", "")
SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM: str = os.getenv("EMAIL_FROM", SMTP_USER or "noreply@example.com")
EMAIL_ENABLED: bool = bool(SMTP_HOST and SMTP_USER)
