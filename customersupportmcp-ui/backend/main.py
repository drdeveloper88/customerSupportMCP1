"""
Customer Support MCP API
========================
Production-grade FastAPI application factory.

Entry point
-----------
    uvicorn main:app --reload --port 8000

API surface
-----------
  GET  /api/v1/health                    liveness probe
  GET  /api/v1/tools                     list agent tools
  GET  /api/v1/orders/{customer_id}      list customer orders
  GET  /api/v1/orders/detail/{order_id}  single order details
  GET  /api/v1/faq?q=...                 knowledge-base search
  POST /api/v1/tickets                   create support ticket
  GET  /api/v1/tickets/{ticket_id}       retrieve ticket
  WS   /api/v1/ws/chat/{customer_id}     real-time AI chat stream
  GET  /api/v1/metrics                   runtime metrics snapshot
  GET  /api/v1/metrics/stream            live metrics via SSE

  POST /api/v1/auth/token                local email+password login
  POST /api/v1/auth/register             create account
  GET  /api/v1/auth/me                   current user profile
  POST /api/v1/auth/forgot-password      request password reset email
  POST /api/v1/auth/reset-password       apply password reset
  GET  /api/v1/auth/oauth/{provider}     initiate OAuth2 (google/facebook)
  GET  /api/v1/auth/oauth/{provider}/callback  OAuth2 callback
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from core.limiter import limiter
from core.logging_config import configure_logging
from core.middleware import JWTAuthMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware

# Logging must be set up before anything imports a logger
configure_logging()
logger = logging.getLogger(__name__)

# Router import must come AFTER configure_logging() and limiter is available
from api.v1.router import router as api_v1_router  # noqa: E402
from core.config import (  # noqa: E402
    ALLOWED_ORIGINS,
    APP_DESCRIPTION,
    APP_TITLE,
    APP_VERSION,
    RATE_LIMIT_AUTH,
    RATE_LIMIT_RESET,
)
from core.database import init_db  # noqa: E402


# ── Application lifespan ────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s %s", APP_TITLE, APP_VERSION)
    try:
        init_db()
        logger.info("Database tables verified / created.")
    except Exception as exc:
        logger.error("Database init failed: %s", exc)
    yield
    logger.info("Shutting down %s", APP_TITLE)


# ── Application factory ──────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    """Construct and configure the FastAPI application."""
    application = FastAPI(
        title=APP_TITLE,
        description=APP_DESCRIPTION,
        version=APP_VERSION,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    # Attach limiter state for slowapi
    application.state.limiter = limiter

    # Rate-limit exceeded handler
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # Middleware (applied in reverse order — last added runs first)
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestContextMiddleware)
    application.add_middleware(JWTAuthMiddleware)
    application.add_middleware(SlowAPIMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    # Versioned API router
    application.include_router(api_v1_router)

    # Global exception handler
    @application.exception_handler(Exception)
    async def _unhandled_exception(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", "-")
        logger.error(
            "Unhandled exception  path=%s  err=%s  [%s]",
            request.url.path, exc, request_id, exc_info=True,
        )
        return JSONResponse(
            status_code=500,
            content={"error": "Internal server error", "request_id": request_id},
        )

    return application


app = create_app()

