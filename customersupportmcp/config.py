"""
Application configuration loaded from .env via python-dotenv.

All public constants are UPPER_SNAKE_CASE to signal they are module-level
configuration values (PEP 8, common industry convention).

LLM Provider priority
---------------------
1. Groq  – fast, free-tier cloud API (requires GROQ_API_KEY)
2. Ollama – local, unlimited, no API key needed (requires Ollama running)

If GROQ_API_KEY is absent the server starts in Ollama-only mode.
If OLLAMA_ENABLED is false and GROQ_API_KEY is absent the server will
refuse to start with an informative error.
"""

import os
import warnings
from pathlib import Path

from dotenv import load_dotenv

# Resolve .env relative to this file so it works regardless of cwd
_ENV_PATH = Path(__file__).resolve().parent / ".env"
load_dotenv(_ENV_PATH)

# ── Groq (primary LLM – free tier) ──────────────────────────────────────────

GROQ_API_KEY: str = os.environ.get("GROQ_API_KEY", "")
if not GROQ_API_KEY:
    warnings.warn(
        "GROQ_API_KEY is not set. Groq will be disabled; Ollama will be used as the "
        "sole LLM provider.  Get a free key at https://console.groq.com",
        stacklevel=1,
    )

# ── Primary model ────────────────────────────────────────────────────────────

GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")

# ── Groq fallback model chain (tried in order on rate-limit / 5xx errors) ────
# All models below are available on Groq's free tier.
# Override via GROQ_FALLBACK_MODELS env var (comma-separated).

_fallback_env = os.getenv("GROQ_FALLBACK_MODELS", "")
GROQ_FALLBACK_MODELS: list[str] = (
    [m.strip() for m in _fallback_env.split(",") if m.strip()]
    if _fallback_env
    else [
        GROQ_MODEL,                                    # llama-3.1-8b-instant (fast, 6K TPM)
        "llama-3.3-70b-versatile",                     # Llama 3.3 70B (12K TPM)
        "meta-llama/llama-4-scout-17b-16e-instruct",   # Llama 4 Scout – separate quota
        "qwen/qwen3-32b",                              # Qwen 3 32B – separate quota
        "openai/gpt-oss-20b",                          # GPT-OSS 20B – separate quota
    ]
)

# ── Ollama (ultimate fallback – local, unlimited, no API key) ─────────────────

OLLAMA_ENABLED: bool = os.getenv("OLLAMA_ENABLED", "true").lower() in ("1", "true", "yes")
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2")

# Guard: refuse to start if no LLM provider is available
if not GROQ_API_KEY and not OLLAMA_ENABLED:
    raise EnvironmentError(
        "No LLM provider available.  Either set GROQ_API_KEY or set OLLAMA_ENABLED=true."
    )

# ── LangSmith (optional observability & tracing) ──────────────────────────────

LANGSMITH_API_KEY: str = os.getenv("LANGCHAIN_API_KEY", "")
LANGSMITH_ENABLED: bool = bool(LANGSMITH_API_KEY)
if LANGSMITH_ENABLED:
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    os.environ.setdefault(
        "LANGCHAIN_PROJECT",
        os.getenv("LANGCHAIN_PROJECT", "customer-support-mcp"),
    )

# ── Rate limiting ─────────────────────────────────────────────────────────────

RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "10"))
RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

# ── Server ────────────────────────────────────────────────────────────────────

SERVER_NAME: str = os.getenv("SERVER_NAME", "CustomerSupportMCP")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
