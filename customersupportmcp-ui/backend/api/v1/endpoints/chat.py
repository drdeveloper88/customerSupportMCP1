"""
GET  /api/v1/tools             – list registered MCP tools
WS   /api/v1/ws/chat/{id}      – real-time streaming chat

WebSocket event protocol (server → client)
──────────────────────────────────────────
{"type": "connected"}
    Sent once after accept to confirm the channel is ready.

{"type": "typing", "status": true|false}
    AI is working / finished working.

{"type": "tool_start", "tool": "<name>", "label": "<friendly text>"}
    Agent is calling a tool (e.g. "🔍 Searching knowledge base…").

{"type": "tool_end", "tool": "<name>"}
    Tool call completed.

{"type": "token", "content": "<chunk>"}
    Individual LLM output token — accumulate on the client for typewriter UX.

{"type": "done", "content": "<full response>"}
    Complete, sanitised final response — use as canonical text.

{"type": "error", "message": "<description>"}
    Unrecoverable error on this turn.
"""

import logging
import re
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services import agent_service
from services.connection_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

# Strip any residual raw tool-call artifacts that might leak to the client
_ARTIFACT_RE = re.compile(
    r"(\(function\s*=\w+>[^)]*\)|</?function[^>]*>|<\|tool_call\|>[^<]*"
    r"|<tool_call>[^<]*</tool_call>|\[TOOL_CALL\][^\n]*)",
    re.IGNORECASE | re.DOTALL,
)


def _sanitise(text: str) -> str:
    cleaned = _ARTIFACT_RE.sub("", text).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned or text


@router.get("/tools", summary="List tools registered in the LangGraph agent")
async def list_tools():
    """Returns all tools available to the AI support agent."""
    return {"tools": agent_service.get_tools()}


@router.websocket("/ws/chat/{customer_id}")
async def websocket_chat(websocket: WebSocket, customer_id: str):
    """
    Real-time AI support chat with token streaming and tool-call progress.

    Uses LangGraph ``astream_events`` v2 to emit tool-start / tool-end /
    token / done events so the React UI can render an interactive thinking
    indicator and a typewriter-style response simultaneously.
    """
    await websocket.accept()
    manager.connect(customer_id, websocket)
    request_id = getattr(websocket.state, "request_id", "-")

    try:
        await websocket.send_json({"type": "connected"})

        while True:
            data = await websocket.receive_json()
            message = str(data.get("message", "")).strip()
            if not message:
                continue

            logger.info(
                "chat  customer=%s  msg_len=%d  [%s]",
                customer_id, len(message), request_id,
            )

            start_time = time.monotonic()
            await websocket.send_json({"type": "typing", "status": True})

            had_error = False

            try:
                async for event in agent_service.stream_chat(customer_id, message):
                    if event["type"] == "done":
                        # Sanitise before delivering final text
                        clean = _sanitise(event.get("content", ""))
                        await websocket.send_json(
                            {"type": "done", "content": clean or "Sorry, no response was generated."}
                        )
                    else:
                        await websocket.send_json(event)
                        if event["type"] == "error":
                            had_error = True

            except Exception as exc:
                logger.error(
                    "WS streaming error  customer=%s  [%s]  err=%s",
                    customer_id, request_id, exc,
                )
                await websocket.send_json(
                    {"type": "error", "message": "Connection error. Please try again."}
                )
                had_error = True

            elapsed_ms = (time.monotonic() - start_time) * 1000
            manager.record_message(elapsed_ms)

            logger.info(
                "chat done  customer=%s  elapsed_ms=%.0f  error=%s  [%s]",
                customer_id, elapsed_ms, had_error, request_id,
            )
            await websocket.send_json({"type": "typing", "status": False})

    except WebSocketDisconnect:
        logger.info("WS disconnected  customer=%s  [%s]", customer_id, request_id)
    except Exception as exc:
        logger.warning("WS unexpected error  customer=%s  err=%s", customer_id, exc)
    finally:
        manager.disconnect(customer_id, websocket)

