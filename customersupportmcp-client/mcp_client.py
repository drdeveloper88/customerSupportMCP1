"""
mcp_client.py
=============
Low-level async wrapper around the CustomerSupportMCP server.

It spawns the server as a subprocess over stdio using FastMCP's Client,
then exposes typed helper methods for every MCP tool.
"""

import sys
from contextlib import asynccontextmanager

from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

from config import MCP_SERVER_PATH


# ── Transport factory ────────────────────────────────────────────────────────

def _make_transport() -> PythonStdioTransport:
    """Launch the MCP server as a subprocess using the current Python interpreter."""
    return PythonStdioTransport(
        script_path=MCP_SERVER_PATH,
        python_cmd=sys.executable,
    )


# ── Context-manager client ───────────────────────────────────────────────────

@asynccontextmanager
async def get_mcp_client():
    """Async context manager that yields a connected FastMCP Client."""
    transport = _make_transport()
    async with Client(transport) as client:
        yield client


# ── Typed tool helpers ───────────────────────────────────────────────────────

async def ask_support_agent(customer_id: str, message: str) -> str:
    """Call handle_customer_request – full AI-powered support pipeline."""
    async with get_mcp_client() as client:
        result = await client.call_tool(
            "handle_customer_request",
            {"customer_id": customer_id, "message": message},
        )
        return _text(result)


async def check_order(order_id: str) -> str:
    """Call check_order – returns full order details as JSON."""
    async with get_mcp_client() as client:
        result = await client.call_tool("check_order", {"order_id": order_id})
        return _text(result)


async def list_orders(customer_id: str) -> str:
    """Call list_orders – returns all orders for a customer as JSON."""
    async with get_mcp_client() as client:
        result = await client.call_tool("list_orders", {"customer_id": customer_id})
        return _text(result)


async def search_faqs(query: str) -> str:
    """Call search_faqs – keyword search over the knowledge base."""
    async with get_mcp_client() as client:
        result = await client.call_tool("search_faqs", {"query": query})
        return _text(result)


async def create_ticket(
    customer_id: str,
    subject: str,
    description: str,
    priority: str = "medium",
) -> str:
    """Call create_ticket – opens a new support ticket."""
    async with get_mcp_client() as client:
        result = await client.call_tool(
            "create_ticket",
            {
                "customer_id": customer_id,
                "subject": subject,
                "description": description,
                "priority": priority,
            },
        )
        return _text(result)


async def get_ticket(ticket_id: str) -> str:
    """Call get_ticket – retrieve a support ticket's details."""
    async with get_mcp_client() as client:
        result = await client.call_tool("get_ticket", {"ticket_id": ticket_id})
        return _text(result)


async def get_customer_profile(customer_id: str) -> str:
    """Call customer_profile – aggregated orders, tickets and spend summary."""
    async with get_mcp_client() as client:
        result = await client.call_tool("customer_profile", {"customer_id": customer_id})
        return _text(result)


async def health_check() -> str:
    """Call health_check – server/DB/LLM provider status."""
    async with get_mcp_client() as client:
        result = await client.call_tool("health_check", {})
        return _text(result)


async def list_server_tools() -> list[str]:
    """Return names of all tools registered on the MCP server."""
    async with get_mcp_client() as client:
        tools = await client.list_tools()
        return [t.name for t in tools]


# ── Internal helper ──────────────────────────────────────────────────────────

def _text(result) -> str:
    """Extract text content from an MCP CallToolResult."""
    if result is None:
        return "(empty response)"
    # FastMCP 3.x: CallToolResult has .data (str) and .content (list)
    if hasattr(result, "data") and result.data is not None:
        return result.data
    if hasattr(result, "content") and result.content:
        parts = []
        for item in result.content:
            if hasattr(item, "text"):
                parts.append(item.text)
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(result)
