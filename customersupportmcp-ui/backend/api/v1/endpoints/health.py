"""GET /api/v1/health – liveness + readiness probe with real component checks."""

import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from core.config import APP_VERSION, APP_TITLE
from services.connection_manager import manager

router = APIRouter(tags=["Health"])

# Recorded at import time so uptime is always relative to server start
_START_TIME = time.time()


@router.get("/health", summary="Liveness + readiness probe")
async def health_check():
    """
    Returns service health including component status.

    Used by load-balancers (liveness), Kubernetes readiness probes,
    and monitoring dashboards.

    Response codes
    --------------
    200  – all components healthy
    503  – one or more components degraded (response body details which)
    """
    components: dict[str, str] = {}
    overall_ok = True

    # ── MCP / Agent availability ──────────────────────────────────────────────
    try:
        from services.agent_service import _AVAILABLE  # type: ignore[import]
        components["agent"] = "ok" if _AVAILABLE else "degraded"
        if not _AVAILABLE:
            overall_ok = False
    except Exception:
        components["agent"] = "unknown"

    # ── SQLite database ───────────────────────────────────────────────────────
    try:
        import sys
        from pathlib import Path
        from core.config import MCP_SERVER_PATH
        _mcp_dir = str(Path(MCP_SERVER_PATH).resolve().parent)
        if _mcp_dir not in sys.path:
            sys.path.insert(0, _mcp_dir)
        from data.database import engine  # type: ignore[import]
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        components["database"] = "ok"
    except Exception as exc:
        components["database"] = f"degraded: {exc}"
        overall_ok = False

    body = {
        "status":           "ok" if overall_ok else "degraded",
        "version":          APP_VERSION,
        "service":          APP_TITLE,
        "uptime_seconds":   int(time.time() - _START_TIME),
        "active_sessions":  manager.active_count,
        "total_messages":   manager.total_messages,
        "components":       components,
    }

    return JSONResponse(
        content=body,
        status_code=200 if overall_ok else 503,
    )

