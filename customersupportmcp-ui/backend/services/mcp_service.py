"""
mcp_service.py — REMOVED

This module used to spawn the MCP server as a subprocess and call it via
PythonStdioTransport / JSON-RPC.  It has been replaced by:

  * ``services.agent_service``   — LangGraph streaming chat (astream_events v2)
  * ``services.support_service`` — direct DB/tool function calls (no transport)

Do not import from this file.
"""

raise ImportError(
    "mcp_service has been removed. "
    "Use agent_service for chat streaming or support_service for data access."
)
