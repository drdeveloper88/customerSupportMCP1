"""
chat.py – Interactive CLI chat client for the CustomerSupportMCP server.

Usage
-----
    python chat.py                      # uses DEFAULT_CUSTOMER_ID from .env
    python chat.py --customer CUST-002  # override customer ID
    python chat.py --customer CUST-001 --tools  # list available tools first

Commands inside the chat
------------------------
    /orders           – List your orders
    /order <id>       – Look up a specific order
    /faq <query>      – Search the FAQ knowledge base
    /ticket <id>      – Get a support ticket's details
    /tools            – Show all MCP tools available on the server
    /help             – Show this help
    /quit or /exit    – Exit the chat
"""

import argparse
import asyncio
import sys
import textwrap

from config import DEFAULT_CUSTOMER_ID
from mcp_client import (
    ask_support_agent,
    check_order,
    get_ticket,
    list_orders,
    list_server_tools,
    search_faqs,
)

# ── ANSI colours (disabled on Windows without ANSI support) ─────────────────
import os

_ANSI = os.name != "nt" or "WT_SESSION" in os.environ or "TERM" in os.environ

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _ANSI else text

CYAN   = lambda t: _c("96", t)
GREEN  = lambda t: _c("92", t)
YELLOW = lambda t: _c("93", t)
BOLD   = lambda t: _c("1",  t)
DIM    = lambda t: _c("2",  t)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _wrap(text: str, width: int = 90) -> str:
    lines = []
    for paragraph in text.split("\n"):
        if paragraph.strip():
            lines.extend(textwrap.wrap(paragraph, width))
        else:
            lines.append("")
    return "\n".join(lines)


def _print_response(label: str, text: str) -> None:
    print(f"\n{CYAN(label)}")
    print(_wrap(text))
    print()


def _print_banner(customer_id: str) -> None:
    print(BOLD("\n╔══════════════════════════════════════════════════╗"))
    print(BOLD("║      ShopEasy Customer Support Chat              ║"))
    print(BOLD("╚══════════════════════════════════════════════════╝"))
    print(f"  Customer : {GREEN(customer_id)}")
    print(f"  Type your question or a command. {DIM('Type /help for commands, /quit to exit.')}\n")


# ── Command handlers ─────────────────────────────────────────────────────────

async def handle_command(cmd: str, customer_id: str) -> bool:
    """Handle a / command. Returns False to signal exit."""
    parts = cmd.strip().split(maxsplit=1)
    keyword = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if keyword in ("/quit", "/exit"):
        print(YELLOW("\nGoodbye! Have a great day.\n"))
        return False

    elif keyword == "/help":
        print(DIM(
            "\nCommands:\n"
            "  /orders           – List your orders\n"
            "  /order <id>       – Look up a specific order (e.g. /order ORD-1001)\n"
            "  /faq <query>      – Search the FAQ knowledge base\n"
            "  /ticket <id>      – Get a support ticket's details\n"
            "  /tools            – Show all tools available on the MCP server\n"
            "  /help             – Show this help\n"
            "  /quit             – Exit the chat\n"
        ))

    elif keyword == "/orders":
        print(DIM("  Fetching your orders..."))
        result = await list_orders(customer_id)
        _print_response("Your Orders:", result)

    elif keyword == "/order":
        if not arg:
            print(YELLOW("  Usage: /order <order_id>  e.g. /order ORD-1001"))
        else:
            print(DIM(f"  Fetching order {arg}..."))
            result = await check_order(arg.strip())
            _print_response(f"Order {arg}:", result)

    elif keyword == "/faq":
        if not arg:
            print(YELLOW("  Usage: /faq <search query>"))
        else:
            print(DIM(f"  Searching FAQs for: {arg}..."))
            result = await search_faqs(arg)
            _print_response("FAQ Results:", result)

    elif keyword == "/ticket":
        if not arg:
            print(YELLOW("  Usage: /ticket <ticket_id>  e.g. /ticket TKT-A1B2C3D4"))
        else:
            print(DIM(f"  Fetching ticket {arg}..."))
            result = await get_ticket(arg.strip())
            _print_response(f"Ticket {arg}:", result)

    elif keyword == "/tools":
        print(DIM("  Fetching available MCP tools..."))
        tools = await list_server_tools()
        print(GREEN("\nAvailable MCP tools:"))
        for name in tools:
            print(f"  • {name}")
        print()

    else:
        print(YELLOW(f"  Unknown command '{keyword}'. Type /help for a list of commands."))

    return True


# ── Main chat loop ────────────────────────────────────────────────────────────

async def chat_loop(customer_id: str) -> None:
    _print_banner(customer_id)

    while True:
        try:
            user_input = input(BOLD("You: ")).strip()
        except (EOFError, KeyboardInterrupt):
            print(YELLOW("\n\nGoodbye!\n"))
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            keep_going = await handle_command(user_input, customer_id)
            if not keep_going:
                break
        else:
            print(DIM("  Agent is thinking..."))
            try:
                response = await ask_support_agent(customer_id, user_input)
                _print_response("Agent:", response)
            except Exception as exc:
                print(YELLOW(f"\n  Error: {exc}\n"))


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Interactive chat client for CustomerSupportMCP"
    )
    parser.add_argument(
        "--customer", "-c",
        default=DEFAULT_CUSTOMER_ID,
        help="Customer ID to use in this session (default: from .env)",
    )
    parser.add_argument(
        "--tools", "-t",
        action="store_true",
        help="List available MCP tools then start chat",
    )
    args = parser.parse_args()

    async def _run():
        if args.tools:
            tools = await list_server_tools()
            print(GREEN("\nAvailable MCP tools:"))
            for name in tools:
                print(f"  • {name}")
            print()
        await chat_loop(args.customer)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
