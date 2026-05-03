"""
Support ticket tools – SQLite real-time backend via SQLAlchemy.

All CRUD operations hit the SQLite database in data/support.db.
Each mutation is wrapped in an explicit transaction for consistency.
"""

import json
import logging
import re

from langchain_core.tools import tool
from sqlalchemy import insert, select, update

from data.database import (
    engine,
    new_ticket_id,
    now_iso,
    ticket_notes_t,
    tickets_t,
)

logger = logging.getLogger(__name__)

_TICKET_ID_RE   = re.compile(r"^TKT-[0-9A-F]{8}$", re.IGNORECASE)
_CUSTOMER_ID_RE = re.compile(r"^CUST-\d+$",          re.IGNORECASE)
_VALID_PRIORITIES = frozenset({"low", "medium", "high", "critical"})
_VALID_STATUSES   = frozenset({"open", "pending", "resolved", "escalated", "closed"})


# ── Internal helpers ──────────────────────────────────────────────────────────

def _fetch_notes(conn, ticket_id: str) -> list[dict]:
    rows = conn.execute(
        select(ticket_notes_t).where(ticket_notes_t.c.ticket_id == ticket_id)
    ).fetchall()
    return [{"note": r.note, "timestamp": r.timestamp} for r in rows]


def _row_to_dict(row, notes: list[dict]) -> dict:
    d = dict(row._mapping)
    d["notes"] = notes
    return d


def create_support_ticket(
    customer_id: str,
    subject: str,
    description: str,
    priority: str = "medium",
) -> dict:
    """Create and persist a new support ticket; return the ticket dict."""
    cid      = customer_id.strip().upper()
    pri      = priority.lower().strip()
    if pri not in _VALID_PRIORITIES:
        pri = "medium"
    tid      = new_ticket_id()
    ts       = now_iso()

    with engine.begin() as conn:
        conn.execute(insert(tickets_t).values(
            ticket_id=tid,
            customer_id=cid,
            subject=subject.strip(),
            description=description.strip(),
            priority=pri,
            status="open",
            created_at=ts,
            updated_at=ts,
            escalated=False,
            escalation_reason=None,
        ))

    logger.info("Ticket %s created for customer %s", tid, cid)
    ticket_data = get_ticket_by_id(tid)  # type: ignore[return-value]

    # Index in the RAG similarity store (best-effort; never blocks ticket creation)
    try:
        from data.rag_store import index_ticket as _rag_index
        _rag_index(ticket_data)
    except Exception as exc:
        logger.debug("RAG ticket indexing skipped: %s", exc)

    return ticket_data


def get_ticket_by_id(ticket_id: str) -> dict | None:
    """Return full ticket dict including notes, or None if not found."""
    tid = ticket_id.strip().upper()
    with engine.connect() as conn:
        row = conn.execute(
            select(tickets_t).where(tickets_t.c.ticket_id == tid)
        ).fetchone()
        if row is None:
            return None
        return _row_to_dict(row, _fetch_notes(conn, tid))


def update_ticket_status(
    ticket_id: str,
    status: str,
    note: str | None = None,
) -> dict | None:
    """Update ticket status and optionally append an audit note."""
    tid = ticket_id.strip().upper()
    st  = status.lower().strip()
    if st not in _VALID_STATUSES:
        st = "open"
    ts  = now_iso()

    with engine.begin() as conn:
        result = conn.execute(
            update(tickets_t)
            .where(tickets_t.c.ticket_id == tid)
            .values(status=st, updated_at=ts)
        )
        if result.rowcount == 0:
            return None
        if note:
            conn.execute(insert(ticket_notes_t).values(
                ticket_id=tid, note=note.strip(), timestamp=ts
            ))

    return get_ticket_by_id(tid)


def do_escalate_ticket(ticket_id: str, reason: str) -> dict | None:
    """Escalate a ticket to HIGH priority and status=escalated."""
    tid = ticket_id.strip().upper()
    ts  = now_iso()

    with engine.begin() as conn:
        result = conn.execute(
            update(tickets_t)
            .where(tickets_t.c.ticket_id == tid)
            .values(
                priority="high",
                status="escalated",
                escalated=True,
                escalation_reason=reason.strip(),
                updated_at=ts,
            )
        )
        if result.rowcount == 0:
            return None
        conn.execute(insert(ticket_notes_t).values(
            ticket_id=tid,
            note=f"Escalated: {reason.strip()}",
            timestamp=ts,
        ))

    logger.info("Ticket %s escalated: %s", tid, reason)
    return get_ticket_by_id(tid)


# ── LangChain @tool definitions ───────────────────────────────────────────────

@tool
def create_ticket_tool(
    customer_id: str,
    subject: str,
    description: str,
    priority: str = "medium",
) -> str:
    """Create a new support ticket for a customer issue that requires follow-up.

    Args:
        customer_id: The customer's ID (e.g. CUST-001).
        subject:     A short title summarising the issue (3-200 chars).
        description: Detailed description of the problem (5-2000 chars).
        priority:    'low', 'medium', 'high', or 'critical'. Defaults to 'medium'.
    """
    ticket = create_support_ticket(customer_id, subject, description, priority)
    return (
        f"Support ticket created successfully!\n"
        f"  Ticket ID: {ticket['ticket_id']}\n"
        f"  Subject  : {ticket['subject']}\n"
        f"  Priority : {ticket['priority']}\n"
        f"  Status   : {ticket['status']}\n"
        f"Our team will respond within 24-48 hours."
    )


@tool
def get_ticket_info(ticket_id: str) -> str:
    """Retrieve the full details and current status of a support ticket.

    Args:
        ticket_id: The ticket ID (e.g. TKT-A1B2C3D4).
    """
    tid = ticket_id.strip().upper()
    if not _TICKET_ID_RE.match(tid):
        return f"Invalid ticket ID format '{ticket_id}'. Expected format: TKT-XXXXXXXX."
    ticket = get_ticket_by_id(tid)
    if not ticket:
        return f"No ticket found with ID '{tid}'."
    return json.dumps(ticket, indent=2, default=str)


@tool
def escalate_ticket_tool(ticket_id: str, reason: str) -> str:
    """Escalate a support ticket to HIGH priority for urgent human-agent review.

    Use this when the customer is extremely frustrated, the issue is critical,
    or it involves safety, legal, or financial concerns.

    Args:
        ticket_id: The ticket ID to escalate (e.g. TKT-A1B2C3D4).
        reason:    Specific reason why escalation is needed.
    """
    tid = ticket_id.strip().upper()
    if not _TICKET_ID_RE.match(tid):
        return f"Invalid ticket ID format '{ticket_id}'. Expected format: TKT-XXXXXXXX."
    ticket = do_escalate_ticket(tid, reason)
    if not ticket:
        return f"Cannot escalate: ticket '{tid}' not found."
    return (
        f"Ticket {tid} escalated to HIGH priority.\n"
        f"  Reason: {reason.strip()}\n"
        f"A senior agent will review this within 2-4 hours."
    )
