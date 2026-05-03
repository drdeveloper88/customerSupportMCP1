"""
Structured logging configuration for the Customer Support MCP API backend.

Features
--------
* Console handler   – human-readable text with request_id injection.
* Rotating JSON file handler – logs/api_server.log, 10 MB × 5 rotations.
* LOG_FORMAT=json   – switches the console formatter to JSON (useful in
  containers / CI pipelines where stdout is ingested by a log aggregator).

Call ``configure_logging()`` once at application startup.
"""

import json
import logging
import logging.handlers
import sys
from datetime import datetime, timezone
from pathlib import Path

from core.config import LOG_LEVEL

_LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


# ── Request-ID filter ─────────────────────────────────────────────────────────
# Must be at module level so uvicorn's multiprocessing reloader can pickle it.

class _RequestIdFilter(logging.Filter):
    """Injects a placeholder request_id into every log record that lacks one."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


# ── JSON formatter ────────────────────────────────────────────────────────────

class _JsonFormatter(logging.Formatter):
    """Emit one JSON object per log line for machine-parseable output."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts":         datetime.now(timezone.utc).isoformat(),
            "level":      record.levelname,
            "logger":     record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message":    record.getMessage(),
        }
        if record.exc_info:
            log_obj["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_obj, ensure_ascii=False)


# ── Public API ────────────────────────────────────────────────────────────────

def configure_logging() -> None:
    """Initialise root logger with request-ID injection, console, and rotating file handler."""
    import os
    use_json_console = os.getenv("LOG_FORMAT", "").lower() == "json"

    level = getattr(logging, LOG_LEVEL, logging.INFO)
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    flt = _RequestIdFilter()

    # ── Console handler ───────────────────────────────────────────────────────
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.addFilter(flt)
    if use_json_console:
        console.setFormatter(_JsonFormatter())
    else:
        console.setFormatter(logging.Formatter(
            fmt="[%(asctime)s] %(levelname)-8s [%(request_id)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))

    # ── Rotating JSON file handler ────────────────────────────────────────────
    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_DIR / "api_server.log",
        maxBytes=10 * 1024 * 1024,   # 10 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(_JsonFormatter())
    file_handler.addFilter(flt)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Silence noisy third-party libraries
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named child logger (convenience wrapper)."""
    return logging.getLogger(name)
