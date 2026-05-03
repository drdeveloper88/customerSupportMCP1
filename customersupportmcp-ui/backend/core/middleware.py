"""
HTTP middleware: request-ID injection, timing, security headers.
"""

import time
import uuid

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from core.logging_config import get_logger

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID to every request/response and log timing."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
        request.state.request_id = request_id

        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000

        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{elapsed_ms:.1f}ms"

        # Skip logging for health-check noise
        if not request.url.path.endswith("/health"):
            logger.info(
                "%s %s → %d  (%.1fms) [%s]",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                request_id,
            )

        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security-oriented HTTP response headers (OWASP recommendations)."""

    _HEADERS: dict[str, str] = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "X-XSS-Protection": "1; mode=block",
    }

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        for header, value in self._HEADERS.items():
            response.headers.setdefault(header, value)
        return response
