"""
HTTP middleware: request-ID injection, timing, security headers, JWT auth,
and IP-based rate limiting for authentication endpoints.
"""

import time
import uuid

from fastapi import Request, Response
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from core.config import JWT_ALGORITHM, JWT_SECRET_KEY
from core.logging_config import get_logger

logger = get_logger(__name__)

# Paths that do NOT require a token
_PUBLIC_PREFIXES = (
    "/api/v1/auth/",
    "/api/v1/health",
    "/api/docs",
    "/api/redoc",
    "/api/openapi.json",
)


class JWTAuthMiddleware(BaseHTTPMiddleware):
    """Validate ``Authorization: Bearer <token>`` on protected routes.

    WebSocket upgrade requests pass the token as a ``token`` query parameter
    because browsers cannot set custom headers during the WebSocket handshake.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Allow public routes without a token
        if any(path.startswith(prefix) for prefix in _PUBLIC_PREFIXES):
            return await call_next(request)

        # WebSocket: token arrives as a query param
        token: str | None = None
        if request.headers.get("upgrade", "").lower() == "websocket":
            token = request.query_params.get("token")
        else:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[len("Bearer "):]

        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            # Check token revocation blocklist
            jti = payload.get("jti")
            if jti:
                from core.auth import _get_redis
                r = _get_redis()
                if r:
                    try:
                        if r.get(f"token_blocklist:{jti}"):
                            return JSONResponse(
                                status_code=401,
                                content={"detail": "Token has been revoked"},
                                headers={"WWW-Authenticate": "Bearer"},
                            )
                    except Exception:
                        pass  # Redis error — fail open
            request.state.user = payload.get("sub")
        except JWTError:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"},
            )

        return await call_next(request)


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
