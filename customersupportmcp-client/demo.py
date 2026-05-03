"""
demo.py – Non-interactive demo that exercises every MCP tool.

Run with:
    python demo.py
"""

import asyncio
import json

from mcp_client import (
    ask_support_agent,
    check_order,
    create_ticket,
    get_customer_profile,
    get_ticket,
    health_check,
    list_orders,
    list_server_tools,
    search_faqs,
)


# ── Formatting helpers ────────────────────────────────────────────────────────

SEP = "─" * 60


def header(title: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")


def section(label: str, content: str) -> None:
    print(f"\n{label}")
    print(SEP)
    try:
        # Pretty-print if JSON
        parsed = json.loads(content)
        print(json.dumps(parsed, indent=2))
    except (json.JSONDecodeError, TypeError):
        print(content)
    print()


# ── Demo scenarios ────────────────────────────────────────────────────────────

async def demo_list_tools() -> None:
    header("1 · Available MCP Tools")
    tools = await list_server_tools()
    for name in tools:
        print(f"  ✓ {name}")


async def demo_faq_search() -> None:
    header("2 · FAQ Search")
    queries = ["how to track my order", "payment declined", "return policy"]
    for q in queries:
        result = await search_faqs(q)
        section(f"Query: '{q}'", result)


async def demo_order_lookup() -> None:
    header("3 · Order Lookup")
    order_ids = ["ORD-1001", "ORD-1002", "ORD-9999"]
    for oid in order_ids:
        result = await check_order(oid)
        section(f"Order: {oid}", result)


async def demo_customer_orders() -> None:
    header("4 · Customer Order History")
    for cid in ["CUST-001", "CUST-003"]:
        result = await list_orders(cid)
        section(f"Customer: {cid}", result)


async def demo_ticket_lifecycle() -> None:
    header("5 · Support Ticket Lifecycle")

    # Create
    print("Creating ticket...")
    result = await create_ticket(
        customer_id="CUST-002",
        subject="Package not delivered",
        description="My order ORD-1003 shows 'processing' but it has been 3 days. I need an update.",
        priority="high",
    )
    section("Created Ticket", result)

    # Extract ticket_id from JSON
    try:
        ticket_data = json.loads(result)
        ticket_id = ticket_data.get("ticket_id")
    except (json.JSONDecodeError, AttributeError):
        ticket_id = None

    if ticket_id:
        print(f"Retrieving ticket {ticket_id}...")
        retrieved = await get_ticket(ticket_id)
        section(f"Retrieved Ticket: {ticket_id}", retrieved)


async def demo_health_check() -> None:
    header("6 · Server Health Check")
    result = await health_check()
    section("Health Status", result)


async def demo_customer_profile() -> None:
    header("7 · Customer Profile (aggregated)")
    for cid in ["CUST-001", "CUST-002"]:
        result = await get_customer_profile(cid)
        section(f"Profile: {cid}", result)


async def demo_ai_agent() -> None:
    header("8 · AI Support Agent (LangGraph + Groq)")

    scenarios = [
        ("CUST-001", "What is your return policy? I want to return my headphones."),
        ("CUST-001", "Can you tell me the tracking information for ORD-1002?"),
        ("CUST-003", "I want a refund for my order ORD-1005, the webcam is defective."),
        ("CUST-002", "I am very frustrated, my order ORD-1003 is still processing after 3 days!"),
    ]

    for customer_id, message in scenarios:
        print(f"\nCustomer ({customer_id}): {message}")
        print(SEP)
        response = await ask_support_agent(customer_id, message)
        print(f"Agent: {response}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    print("\n" + "█" * 60)
    print("  CustomerSupportMCP – Full Demo")
    print("█" * 60)

    await demo_list_tools()
    await demo_health_check()
    await demo_faq_search()
    await demo_order_lookup()
    await demo_customer_orders()
    await demo_customer_profile()
    await demo_ticket_lifecycle()
    await demo_ai_agent()

    print("\n" + "═" * 60)
    print("  Demo complete.")
    print("═" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
