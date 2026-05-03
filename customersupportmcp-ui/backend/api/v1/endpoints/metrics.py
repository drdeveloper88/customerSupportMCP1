"""
GET /api/v1/metrics        – point-in-time snapshot (JSON)
GET /api/v1/metrics/stream – live push via Server-Sent Events (1 s interval)

Resume highlight: real-time observability with zero polling on the client —
the browser keeps a single SSE connection and receives live stats every second.
"""

import asyncio
import json
import time

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from services.connection_manager import manager

router = APIRouter(tags=["Metrics"])


@router.get("/metrics", summary="Application metrics snapshot")
async def get_metrics() -> dict:
    """
    Return a point-in-time snapshot of runtime metrics.

    Fields
    ------
    active_connections  – number of live WebSocket sessions
    active_customers    – customer IDs currently connected
    total_messages      – cumulative AI responses served
    avg_response_ms     – average end-to-end latency (ms)
    uptime_seconds      – seconds since the server started
    timestamp           – Unix epoch of this snapshot
    """
    return {**manager.stats(), "timestamp": time.time()}


@router.get(
    "/metrics/stream",
    summary="Live metrics via Server-Sent Events",
    response_class=StreamingResponse,
)
async def stream_metrics():
    """
    Push live application metrics to the client every second using
    `Server-Sent Events <https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events>`_.

    Connect with::

        const es = new EventSource('/api/v1/metrics/stream');
        es.onmessage = (e) => console.log(JSON.parse(e.data));

    Each event is a JSON object with the same fields as ``GET /api/v1/metrics``.
    The stream runs indefinitely; close the connection from the client side when done.
    """

    async def _generate():
        while True:
            payload = {**manager.stats(), "timestamp": time.time()}
            # SSE format: "data: <json>\n\n"
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering for SSE
            "Connection":        "keep-alive",
        },
    )
