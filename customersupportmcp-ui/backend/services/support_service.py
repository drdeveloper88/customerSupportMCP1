"""
Direct support service — calls the MCP server's tools and DB functions
without going through MCP transport (no subprocess, no JSON-RPC overhead).

This is the modern replacement for the old mcp_service.py that spawned the
MCP server as a subprocess. We import the Python functions directly — same
process, zero latency, full type-safety.

Blocking SQLAlchemy calls are wrapped in ``asyncio.to_thread`` so they never
block the FastAPI event loop.
"""

import asyncio
import logging
import sys
from pathlib import Path

from core.config import MCP_SERVER_PATH

logger = logging.getLogger(__name__)

# ── Bootstrap: make the MCP server package importable once ───────────────────
_MCP_SERVER_DIR = Path(MCP_SERVER_PATH).resolve().parent
if str(_MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_SERVER_DIR))

# Direct imports — no subprocess, no MCP transport
from data.database import init_db                                        # noqa: E402
from tools.kb_tools import search_kb                                     # noqa: E402
from tools.order_tools import get_order_by_id, get_orders_by_customer   # noqa: E402
from tools.ticket_tools import create_support_ticket, get_ticket_by_id  # noqa: E402
from data.database import get_analytics_data                             # noqa: E402

# Ensure tables exist and seed data is present (idempotent)
init_db()
logger.info("Support service ready — direct DB mode (%s)", _MCP_SERVER_DIR)


# ── Orders ────────────────────────────────────────────────────────────────────

async def fetch_orders(customer_id: str) -> list[dict]:
    """Return all orders for *customer_id* from SQLite."""
    return await asyncio.to_thread(get_orders_by_customer, customer_id)


async def fetch_order(order_id: str) -> dict | None:
    """Return a single order by *order_id*, or ``None`` if not found."""
    return await asyncio.to_thread(get_order_by_id, order_id)


# ── Knowledge base ────────────────────────────────────────────────────────────

async def search_faq(query: str, max_results: int = 3) -> list[dict]:
    """Full-text keyword search over the knowledge-base JSON file."""
    if not query.strip():
        return []
    return await asyncio.to_thread(search_kb, query, max_results)


# ── Tickets ───────────────────────────────────────────────────────────────────

async def open_ticket(
    customer_id: str,
    subject: str,
    description: str,
    priority: str = "medium",
) -> dict:
    """Create a support ticket and return the full ticket dict."""
    return await asyncio.to_thread(
        create_support_ticket, customer_id, subject, description, priority
    )


async def fetch_ticket(ticket_id: str) -> dict | None:
    """Return a ticket by *ticket_id*, or ``None`` if not found."""
    return await asyncio.to_thread(get_ticket_by_id, ticket_id)


# ── Analytics ─────────────────────────────────────────────────────────────────

async def get_analytics() -> dict:
    """Return aggregated analytics data for the dashboard."""
    from services.connection_manager import manager

    data = await asyncio.to_thread(get_analytics_data)
    data["server"] = manager.stats()
    return data
