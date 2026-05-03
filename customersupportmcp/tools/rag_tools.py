"""
RAG-powered LangGraph tools.

find_similar_tickets_tool  — surfaces existing tickets similar to a new
                             issue before the agent creates a duplicate.
"""

import logging

from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def find_similar_tickets_tool(subject: str, description: str) -> str:
    """Find existing support tickets similar to the described issue.

    Call this BEFORE creating a new support ticket to:
    • Avoid creating duplicate tickets for the same problem.
    • Surface related tickets so you can reference them in your reply.
    • Identify recurring issues that may warrant escalation.

    Args:
        subject:     Short title of the issue (e.g. "package not delivered").
        description: Full description of the customer's problem.
    """
    try:
        from data.rag_store import find_similar_tickets
    except ImportError:
        return (
            "Ticket similarity search is unavailable "
            "(chromadb or sentence-transformers not installed)."
        )

    query   = f"{subject} {description}"
    similar = find_similar_tickets(query, k=3)

    if not similar:
        return (
            "No similar tickets found. "
            "This appears to be a unique issue — safe to create a new ticket."
        )

    lines = [f"Found {len(similar)} similar existing ticket(s):"]
    for t in similar:
        score = f"{t['similarity_score']:.0%}"
        lines.append(
            f"  • {t['ticket_id']} ({score} match) — \"{t['subject']}\""
            f"  [Priority: {t['priority']}, Status: {t['status']}]"
        )
    lines.append(
        "\nReview the above before creating a new ticket. "
        "If the customer's issue matches an existing open ticket, reference it instead."
    )

    return "\n".join(lines)
