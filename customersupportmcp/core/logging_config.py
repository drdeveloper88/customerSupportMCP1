"""
Centralised logging configuration for the CustomerSupportMCP MCP server.

Features
--------
* Console handler  – human-readable text, written to stderr (stdout is the
  JSON-RPC transport channel and must stay clean).
* Rotating file handler – JSON-structured lines in logs/mcp_server.log,
  capped at 10 MB × 5 rotations.
* LOG_FORMAT=json  env var switches the console to JSON as well (CI/CD).

Call ``configure_logging()`` once at startup before any other import that
may trigger logging.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

from config import LOG_LEVEL

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


# ── JSON formatter ────────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for machine-parseable output."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts":      datetime.now(timezone.utc).isoformat(),
            "level":   record.levelname,
            "logger":  record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


# ── Public API ────────────────────────────────────────────────────────────────

def configure_logging() -> None:
    """Initialise root logger with console (stderr) + rotating JSON file handler."""
    import os
    use_json_console = os.getenv("LOG_FORMAT", "").lower() == "json"

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ── Console handler (stderr — never stdout) ───────────────────────────────
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(level)
    if use_json_console:
        console.setFormatter(_JsonFormatter())
    else:
        console.setFormatter(logging.Formatter(
            fmt="[%(asctime)s] %(levelname)-8s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    # ── Rotating JSON file handler ────────────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "mcp_server.log",
        maxBytes=10 * 1024 * 1024,   # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    # Remove any handlers BasicConfig may have added before us
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Silence noisy third-party libraries
    for noisy in ("httpx", "httpcore", "langchain", "langgraph", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger (convenience wrapper)."""
    return logging.getLogger(name)


# Module-level convenience logger
logger = logging.getLogger("customer_support_mcp")
