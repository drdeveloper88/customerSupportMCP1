"""
Direct agent service — LangGraph streaming path.

Imports the LangGraph ReAct agent directly (same process, no subprocess) so
the WebSocket endpoint can stream tool-call events and LLM tokens in real time
using ``astream_events`` v2.

MCP server code is located at ``MCP_SERVER_PATH`` (set in .env).
"""

import logging
import sys
from pathlib import Path
from typing import AsyncGenerator

from core.config import MCP_SERVER_PATH

logger = logging.getLogger(__name__)

# ── Bootstrap: make the MCP server package importable once ───────────────────
# support_service.py may already have done this; the guard makes it idempotent.
_MCP_SERVER_DIR = Path(MCP_SERVER_PATH).resolve().parent
if str(_MCP_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_MCP_SERVER_DIR))

try:
    from agent.graph import (                              # type: ignore[import]
        _TOOL_LABELS,
        _TOOLS,
        stream_support_agent as _stream,
    )
    _AVAILABLE = True
    logger.info("LangGraph agent loaded from %s", _MCP_SERVER_DIR)
except Exception as _import_err:                           # noqa: BLE001
    _AVAILABLE = False
    _TOOLS = []
    _TOOL_LABELS = {}
    logger.warning("LangGraph agent unavailable: %s", _import_err)


# ── Public API ────────────────────────────────────────────────────────────────

def get_tools() -> list[dict]:
    """Return descriptors of every tool registered in the LangGraph agent."""
    return [
        {
            "name":        t.name,
            "description": t.description,
            "label":       _TOOL_LABELS.get(t.name, t.name),
        }
        for t in _TOOLS
    ]


async def stream_chat(
    customer_id: str,
    message: str,
) -> AsyncGenerator[dict, None]:
    """
    Async generator that yields real-time agent events via ``astream_events`` v2.

    Event shapes
    ------------
    ``{"type": "tool_start", "tool": <name>, "label": <friendly text>}``
    ``{"type": "tool_end",   "tool": <name>}``
    ``{"type": "token",      "content": <text chunk>}``
    ``{"type": "done",       "content": <full response>}``
    ``{"type": "error",      "message": <description>}``
    """
    if not _AVAILABLE:
        yield {"type": "error", "message": "Streaming agent not available."}
        return

    async for event in _stream(customer_id, message):
        yield event
