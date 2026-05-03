"""Customer profile aggregation tool.

Provides the agent with a single-call snapshot of a customer's
full history: order summary, open tickets, and total spend.
"""

import json
import logging

from langchain_core.tools import tool
from sqlalchemy import func, select

from data.database import (
    engine,
    get_conversation_history,
    order_items_t,
    orders_t,
    tickets_t,
)

logger = logging.getLogger(__name__)


@tool
def get_customer_profile(customer_id: str) -> str:
    """Return a comprehensive summary of a customer's orders and support tickets.

    Use this tool at the start of a session to quickly understand the customer's
    history before addressing their specific request.

    Args:
        customer_id: The unique customer identifier.

    Returns:
        JSON string with keys: customer_id, total_orders, total_spend,
        recent_orders (last 5), open_tickets, conversation_turns.
    """
    cid = customer_id.strip().upper()
    profile: dict = {"customer_id": cid}

    try:
        with engine.connect() as conn:
            # ── Order summary ─────────────────────────────────────────────────
            order_rows = conn.execute(
                select(orders_t).where(orders_t.c.customer_id == cid)
                .order_by(orders_t.c.created_at.desc())
            ).fetchall()

            total_spend = sum(float(r.total or 0) for r in order_rows)
            status_counts: dict[str, int] = {}
            for r in order_rows:
                status_counts[r.status] = status_counts.get(r.status, 0) + 1

            recent_orders = []
            for r in order_rows[:5]:
                items_rows = conn.execute(
                    select(order_items_t).where(
                        order_items_t.c.order_id == r.order_id
                    )
                ).fetchall()
                recent_orders.append({
                    "order_id":   r.order_id,
                    "status":     r.status,
                    "total":      round(float(r.total or 0), 2),
                    "created_at": r.created_at,
                    "item_count": len(items_rows),
                    "tracking":   r.tracking_number,
                })

            profile["total_orders"] = len(order_rows)
            profile["total_spend"]  = round(total_spend, 2)
            profile["order_status_breakdown"] = status_counts
            profile["recent_orders"] = recent_orders

            # ── Open / escalated tickets ──────────────────────────────────────
            open_tickets = conn.execute(
                select(tickets_t).where(
                    tickets_t.c.customer_id == cid,
                ).order_by(tickets_t.c.created_at.desc()).limit(10)
            ).fetchall()

            profile["open_tickets"] = [
                {
                    "ticket_id": t.ticket_id,
                    "subject":   t.subject,
                    "status":    t.status,
                    "priority":  t.priority,
                    "escalated": bool(t.escalated),
                    "created_at": t.created_at,
                }
                for t in open_tickets
                if t.status not in ("resolved", "closed")
            ]
            profile["total_tickets"] = len(open_tickets)

        # ── Recent conversation turns ─────────────────────────────────────────
        history = get_conversation_history(cid, limit=6)
        profile["recent_conversation_turns"] = len(history)

        return json.dumps(profile, indent=2)

    except Exception as exc:
        logger.error("get_customer_profile error for %s: %s", cid, exc, exc_info=True)
        return json.dumps({"error": f"Could not load profile for {cid}: {exc}"})
