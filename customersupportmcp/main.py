"""
Customer Support MCP Server
============================
FastMCP server exposing customer-support capabilities to any MCP client
(Claude Desktop, VS Code Copilot, custom agents, etc.).

Exposed MCP tools
-----------------
handle_customer_request  – Full AI-powered support via LangGraph + Groq/Ollama
customer_profile         – Aggregate customer orders + tickets in one call
check_order              – Direct order lookup
list_orders              – All orders for a customer
create_ticket            – Open a support ticket
get_ticket               – Retrieve ticket details
search_faqs              – Search the knowledge base
health_check             – Server / DB / LLM health status

Run
---
    python main.py                        # stdio transport (MCP clients)
    fastmcp run main.py --transport stdio # explicit stdio
"""

import json
import logging
import time

from fastmcp import FastMCP

from agent.graph import run_support_agent
from config import GROQ_API_KEY, GROQ_FALLBACK_MODELS, OLLAMA_ENABLED, OLLAMA_MODEL, SERVER_NAME
from core.logging_config import configure_logging
from core.rate_limiter import rate_limiter
from data.database import engine, init_db
from gateway.middleware import gateway
from tools.customer_tools import get_customer_profile as _get_customer_profile
from tools.kb_tools import search_kb
from tools.order_tools import get_order_by_id, get_orders_by_customer
from tools.ticket_tools import create_support_ticket, get_ticket_by_id

# Configure logging before anything else
configure_logging()
logger = logging.getLogger(__name__)

# Initialise the SQLite database (creates tables + seeds data on first run)
init_db()

_llm_chain = " \u2192 ".join(GROQ_FALLBACK_MODELS) + (" \u2192 ollama/" + OLLAMA_MODEL if OLLAMA_ENABLED else "")
logger.info("Starting %s | LLM chain: %s", SERVER_NAME, _llm_chain)

# ── Server setup ─────────────────────────────────────────────────────────────

mcp = FastMCP(
    name=SERVER_NAME,
    instructions=(
        "This MCP server provides AI-powered customer support tools for an e-commerce platform. "
        "Use handle_customer_request for natural-language support queries. "
        "Use customer_profile at the start of a session to get full context. "
        "Use health_check to verify server status. "
        "Use the other tools for direct, structured data access."
    ),
)

# ── MCP tools ────────────────────────────────────────────────────────────────


@mcp.tool()
@gateway(key_arg="customer_id")
async def handle_customer_request(customer_id: str, message: str) -> str:
    """Process a customer support request using an AI agent (LangGraph + Groq/Ollama).

    The agent understands natural language, looks up orders, searches FAQs,
    creates tickets, processes refunds, and escalates when needed.
    Automatically falls back from Groq to Ollama on quota / rate-limit errors.
    Per-customer rate limiting is enforced by the gateway middleware.
    Conversation history is maintained across requests for the same customer_id.

    Args:
        customer_id: The customer's unique ID (e.g. CUST-001).
        message: The customer's question or issue description.
    """
    return await run_support_agent(customer_id, message)


@mcp.tool()
def customer_profile(customer_id: str) -> str:
    """Get a comprehensive profile for a customer: orders, open tickets, total spend.

    Returns a JSON summary useful for understanding the customer's history
    before handling their support request.

    Args:
        customer_id: The customer's unique ID (e.g. CUST-001).
    """
    return _get_customer_profile.invoke({"customer_id": customer_id})


@mcp.tool()
def check_order(order_id: str) -> str:
    """Return full details of a single order.

    Args:
        order_id: The order ID to look up (e.g. ORD-1001).
    """
    order = get_order_by_id(order_id)
    if not order:
        return f"Order '{order_id}' not found. Please check the order ID."
    return json.dumps(order, indent=2, default=str)


@mcp.tool()
def list_orders(customer_id: str) -> str:
    """List all orders placed by a customer.

    Args:
        customer_id: The customer's unique ID (e.g. CUST-001).
    """
    orders = get_orders_by_customer(customer_id)
    if not orders:
        return f"No orders found for customer '{customer_id}'."
    return json.dumps(orders, indent=2, default=str)


@mcp.tool()
def create_ticket(
    customer_id: str,
    subject: str,
    description: str,
    priority: str = "medium",
) -> str:
    """Create a new customer support ticket.

    Args:
        customer_id: The customer's ID.
        subject: Short title for the issue.
        description: Full description of the problem.
        priority: 'low', 'medium', 'high', or 'critical'. Defaults to 'medium'.
    """
    ticket = create_support_ticket(customer_id, subject, description, priority)
    return json.dumps(ticket, indent=2, default=str)


@mcp.tool()
def get_ticket(ticket_id: str) -> str:
    """Get the status and details of a support ticket.

    Args:
        ticket_id: The ticket ID (e.g. TKT-A1B2C3D4).
    """
    ticket = get_ticket_by_id(ticket_id)
    if not ticket:
        return f"Ticket '{ticket_id}' not found."
    return json.dumps(ticket, indent=2)


@mcp.tool()
def search_faqs(query: str) -> str:
    """Search the FAQ knowledge base for answers to common questions.

    Args:
        query: Search terms or a customer question.
    """
    results = search_kb(query)
    if not results:
        return "No FAQ articles found matching your query."
    return json.dumps(results, indent=2)


@mcp.tool()
def health_check() -> str:
    """Return the health status of the server, database, and LLM providers.

    Checks:
    - Database connectivity
    - Configured LLM providers (Groq key present, Ollama enabled)
    - Rate limiter stats

    Returns a JSON document with a top-level 'status' of 'ok' or 'degraded'.
    """
    checks: dict = {}
    overall_ok = True

    # ── Database ──────────────────────────────────────────────────────────────
    try:
        t0 = time.monotonic()
        with engine.connect() as conn:
            conn.execute(__import__("sqlalchemy").text("SELECT 1"))
        checks["database"] = {"status": "ok", "latency_ms": round((time.monotonic() - t0) * 1000, 1)}
    except Exception as exc:
        checks["database"] = {"status": "error", "detail": str(exc)}
        overall_ok = False

    # ── LLM providers ─────────────────────────────────────────────────────────
    checks["llm"] = {
        "groq": {
            "enabled": bool(GROQ_API_KEY),
            "models":  GROQ_FALLBACK_MODELS if GROQ_API_KEY else [],
        },
        "ollama": {
            "enabled": OLLAMA_ENABLED,
            "model":   OLLAMA_MODEL if OLLAMA_ENABLED else None,
        },
        "any_provider_available": bool(GROQ_API_KEY) or OLLAMA_ENABLED,
    }
    if not checks["llm"]["any_provider_available"]:
        overall_ok = False

    # ── Rate limiter ──────────────────────────────────────────────────────────
    checks["rate_limiter"] = {
        "max_requests_per_window": rate_limiter.max_requests,
        "window_seconds":          rate_limiter.window_seconds,
        "active_keys":             len(rate_limiter._calls),  # noqa: SLF001
    }

    result = {
        "status":  "ok" if overall_ok else "degraded",
        "server":  SERVER_NAME,
        "checks":  checks,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat() + "Z",
    }
    return json.dumps(result, indent=2)


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
