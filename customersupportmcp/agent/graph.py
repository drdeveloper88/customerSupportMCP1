"""
LangGraph ReAct agent that powers the AI customer-support logic.

LLM Fallback Strategy
---------------------
Requests are tried against providers in this priority order:

1. **Groq** – fast cloud API (free tier).  All models in
   ``GROQ_FALLBACK_MODELS`` are tried sequentially on rate-limit /
   transient server errors (HTTP 429 / 5xx).
2. **Ollama** – local model, unlimited, no API key required.
   Used when all Groq models are exhausted **or** when
   ``GROQ_API_KEY`` is absent.

Streaming
---------
``stream_support_agent()`` yields real-time events using LangGraph's
``astream_events`` v2 API:
  - tool_start / tool_end  – shows the user what the agent is doing
  - token                  – individual LLM output tokens for typewriter UX
  - done                   – full accumulated response (for reliability)
  - error                  – on unrecoverable failure

LangSmith Tracing
-----------------
Set ``LANGCHAIN_API_KEY`` in your ``.env`` to enable automatic run
tracing in LangSmith.  No code changes are needed – the LangChain
callback machinery picks up the env vars set in ``config.py``.
"""

import asyncio
import logging
import re
from pathlib import Path
from typing import AsyncGenerator

from langchain_core.messages import SystemMessage
from langchain_groq import ChatGroq
from langgraph.prebuilt import create_react_agent

from config import (
    GROQ_API_KEY,
    GROQ_FALLBACK_MODELS,
    OLLAMA_BASE_URL,
    OLLAMA_ENABLED,
    OLLAMA_MODEL,
)
from data.database import get_conversation_history, save_conversation_turn
from tools.customer_tools import get_customer_profile
from tools.kb_tools import search_knowledge_base
from tools.order_tools import check_order_status, list_customer_orders, process_refund
from tools.rag_tools import find_similar_tickets_tool
from tools.ticket_tools import (
    create_ticket_tool,
    escalate_ticket_tool,
    get_ticket_info,
)

logger = logging.getLogger(__name__)

# ── Hallucination guard ───────────────────────────────────────────────────────
# Patterns that indicate the LLM hallucinated a raw function-call instead of
# invoking the tool through the proper ReAct mechanism.
_RAW_TOOL_CALL_RE = re.compile(
    r"(\(function\s*=|\bfunction_calls\b|<tool_call>|<\|tool_call\|>|"
    r"\btool_call\b.*\{|\[TOOL_CALL\])",
    re.IGNORECASE,
)

# ── Tool friendly labels (shown in the UI during streaming) ───────────────────
_TOOL_LABELS: dict[str, str] = {
    "search_knowledge_base":      "🔍 Searching knowledge base…",
    "find_similar_tickets_tool":  "🧠 Checking for similar tickets…",
    "check_order_status":         "📦 Looking up order details…",
    "list_customer_orders":       "📋 Fetching customer orders…",
    "process_refund":             "💳 Processing refund…",
    "create_ticket_tool":         "🎫 Creating support ticket…",
    "get_ticket_info":            "🔎 Retrieving ticket details…",
    "escalate_ticket_tool":       "🚨 Escalating to human agent…",
    "get_customer_profile":       "👤 Loading customer profile…",
}

# ── System prompt (loaded from file; inline fallback if file is absent) ───────

_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"
_SYSTEM_PROMPT_FALLBACK = (
    "You are a professional, empathetic customer support agent for ShopEasy. "
    "Resolve customer issues efficiently and politely using the available tools."
)


def _load_system_prompt() -> str:
    """Read the system prompt from ``prompts/system_prompt.txt``."""
    if _PROMPT_FILE.exists():
        text = _PROMPT_FILE.read_text(encoding="utf-8").strip()
        if text:
            logger.debug("Loaded system prompt from %s", _PROMPT_FILE)
            return text
    logger.warning("System prompt file not found at %s; using inline fallback.", _PROMPT_FILE)
    return _SYSTEM_PROMPT_FALLBACK


_SYSTEM_PROMPT: str = _load_system_prompt()

# ── Agent tools ───────────────────────────────────────────────────────────────

_TOOLS = [
    get_customer_profile,
    search_knowledge_base,
    find_similar_tickets_tool,
    check_order_status,
    list_customer_orders,
    process_refund,
    create_ticket_tool,
    get_ticket_info,
    escalate_ticket_tool,
]

# ── Agent factories ───────────────────────────────────────────────────────────


def _build_agent_groq(model_name: str):
    """Construct a LangGraph ReAct agent backed by a Groq-hosted model.

    Args:
        model_name: A valid Groq model identifier (e.g. ``"llama-3.1-8b-instant"``).
    """
    llm = ChatGroq(
        model=model_name,
        temperature=0,
        api_key=GROQ_API_KEY,
        max_retries=0,  # retries are handled by the fallback chain in run_support_agent
    )
    return create_react_agent(
        model=llm,
        tools=_TOOLS,
        prompt=SystemMessage(content=_SYSTEM_PROMPT),
    )


def _build_agent_ollama():
    """Construct a LangGraph ReAct agent backed by a local Ollama model.

    Ollama must be running at ``OLLAMA_BASE_URL`` (default: http://localhost:11434).
    Pull the model first with: ``ollama pull <OLLAMA_MODEL>``
    """
    try:
        from langchain_ollama import ChatOllama  # lazy import – optional dep
    except ImportError as exc:
        raise ImportError(
            "langchain-ollama is not installed.  "
            "Run: pip install langchain-ollama"
        ) from exc

    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0,
    )
    return create_react_agent(
        model=llm,
        tools=_TOOLS,
        prompt=SystemMessage(content=_SYSTEM_PROMPT),
    )


# Keep backward-compat alias used by older code / tests
def _build_agent(model_name: str):
    """Alias for :func:`_build_agent_groq` (backward compatibility)."""
    return _build_agent_groq(model_name)


def _extract_text(content) -> str:
    """Coerce LangChain content (str or list of blocks) to a plain string."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return " ".join(parts).strip()
    return str(content)


def _is_clean_final_response(msg) -> bool:
    """Return True only for a genuine final AI message (no pending tool calls,
    no hallucinated raw-function-call syntax)."""
    if getattr(msg, "type", None) != "ai":
        return False
    # Messages that still have pending tool_calls are intermediate steps
    if getattr(msg, "tool_calls", None):
        return False
    text = _extract_text(msg.content)
    if not text.strip():
        return False
    # Reject if the model hallucinated raw function-call syntax
    if _RAW_TOOL_CALL_RE.search(text):
        logger.warning("Skipping AI message with hallucinated tool-call syntax: %.120s", text)
        return False
    return True


def _is_retriable_error(exc: Exception) -> bool:
    """Return True for errors that warrant trying the next model."""
    err_lower = str(exc).lower()
    # Transient errors: rate limits, server errors
    transient = any(
        token in err_lower
        for token in ("rate_limit", "ratelimit", "429", "quota", "overloaded", "503", "502")
    )
    # Permanent model-level errors: decommissioned / deprecated / not found
    model_gone = any(
        token in err_lower
        for token in ("decommissioned", "deprecated", "model_not_found", "does not exist",
                      "no longer supported", "model not found")
    )
    # Connection errors: provider not reachable (Ollama not running, network issue)
    connection_error = any(
        token in err_lower
        for token in ("connecterror", "connection", "all connection attempts failed",
                      "connect error", "connection refused", "name or service not known",
                      "failed to establish", "network is unreachable")
    )
    return transient or model_gone or connection_error


# Maximum seconds we will wait for a rate-limit window to expire before retrying.
_RATE_LIMIT_MAX_WAIT: float = 35.0


def _is_rate_limit_error(exc: Exception) -> bool:
    """Return True when the error is a transient rate-limit / quota (HTTP 429)."""
    err_lower = str(exc).lower()
    return any(
        t in err_lower
        for t in ("rate_limit", "ratelimit", "429", "quota", "overloaded")
    )


def _extract_retry_after(exc: Exception) -> float | None:
    """Parse the retry-after delay from a Groq 429 message.

    Groq error messages contain text like:
        "Please try again in 8.21s."
        "Please try again in 320ms."
    Returns the delay in seconds, or ``None`` if not found.
    """
    m = re.search(r"try again in (\d+(?:\.\d+)?)(s|ms)", str(exc), re.IGNORECASE)
    if m:
        value, unit = float(m.group(1)), m.group(2).lower()
        return value if unit == "s" else value / 1000.0
    return None


# ── Public interface ──────────────────────────────────────────────────────────


async def run_support_agent(customer_id: str, message: str) -> str:
    """Run the ReAct agent and return its final response text.

    Provider fallback order
    -----------------------
    1. Each model in ``GROQ_FALLBACK_MODELS`` (if ``GROQ_API_KEY`` is set).
    2. Local Ollama model (if ``OLLAMA_ENABLED`` is true).

    Rate-limit and transient server errors trigger the next provider;
    non-retriable errors surface a safe message immediately.

    Args:
        customer_id: Unique customer identifier (injected as context).
        message:     The customer's natural-language support request.

    Returns:
        Final AI response string.
    """
    user_input = f"[Customer ID: {customer_id}]\n\n{message}"

    # ── Build message list with conversation history ───────────────────────────
    # Pass up to 10 previous turns so the agent has multi-turn context.
    history = get_conversation_history(customer_id, limit=10)
    messages: list[tuple[str, str]] = [
        (turn["role"] if turn["role"] == "assistant" else "human", turn["content"])
        for turn in history
    ]
    messages.append(("human", user_input))

    # Build ordered list of (provider_label, builder_callable) to attempt
    candidates: list[tuple[str, object]] = []
    if GROQ_API_KEY:
        for model in GROQ_FALLBACK_MODELS:
            candidates.append((f"groq/{model}", lambda m=model: _build_agent_groq(m)))
    if OLLAMA_ENABLED:
        candidates.append((f"ollama/{OLLAMA_MODEL}", _build_agent_ollama))

    if not candidates:
        return (
            "No LLM provider is configured.  "
            "Please set GROQ_API_KEY or enable Ollama (OLLAMA_ENABLED=true)."
        )

    prev_label: str | None = None
    rate_limited_retry: list[tuple[float, str, object]] = []  # (wait_secs, label, build_fn)

    for idx, (label, build_fn) in enumerate(candidates):
        try:
            if prev_label is not None:
                logger.warning("Provider '%s' unavailable – switching to '%s'", prev_label, label)

            agent = build_fn()
            result = await agent.ainvoke({"messages": messages})

            # Find the last clean final AI message (skip intermediate tool-call steps
            # and any message where the model hallucinated raw function-call syntax).
            for msg in reversed(result["messages"]):
                if _is_clean_final_response(msg):
                    text = _extract_text(msg.content)
                    if idx > 0:
                        logger.info("Request served successfully by fallback provider '%s'", label)
                    # ── Persist conversation turn ─────────────────────────────
                    try:
                        save_conversation_turn(customer_id, "user", message)
                        save_conversation_turn(customer_id, "assistant", text)
                    except Exception as db_exc:  # noqa: BLE001
                        logger.warning("Failed to save conversation history: %s", db_exc)
                    return text

            return "I'm sorry, I was unable to process your request. Please try again."

        except Exception as exc:  # noqa: BLE001
            retry_after = _extract_retry_after(exc) if _is_rate_limit_error(exc) else None
            if retry_after is not None:
                logger.warning(
                    "Provider '%s' rate limited (retry in %.1fs) – trying next provider",
                    label, retry_after,
                )
                rate_limited_retry.append((retry_after, label, build_fn))
            else:
                logger.warning("Provider '%s' failed (%s) – trying next provider", label, exc)
            prev_label = label

    # ── All candidates exhausted on first pass ────────────────────────────────
    # If some were only rate-limited, wait for the shortest window and retry once.
    if rate_limited_retry:
        max_wait = max(d for d, *_ in rate_limited_retry)
        wait_secs = min(max_wait + 2.0, _RATE_LIMIT_MAX_WAIT)
        logger.warning(
            "All providers rate limited. Waiting %.1fs before retrying %d provider(s).",
            wait_secs, len(rate_limited_retry),
        )
        await asyncio.sleep(wait_secs)

        for _delay, label, build_fn in sorted(rate_limited_retry, key=lambda x: x[0]):
            try:
                logger.info("Retrying rate-limited provider '%s'", label)
                agent = build_fn()
                result = await agent.ainvoke({"messages": messages})
                for msg in reversed(result["messages"]):
                    if _is_clean_final_response(msg):
                        text = _extract_text(msg.content)
                        logger.info("Rate-limit retry succeeded with provider '%s'", label)
                        try:
                            save_conversation_turn(customer_id, "user", message)
                            save_conversation_turn(customer_id, "assistant", text)
                        except Exception as db_exc:  # noqa: BLE001
                            logger.warning("Failed to save conversation history: %s", db_exc)
                        return text
                return "I'm sorry, I was unable to process your request. Please try again."
            except Exception as exc:  # noqa: BLE001
                logger.warning("Retry of provider '%s' also failed: %s", label, exc)

    logger.critical("All %d LLM providers in fallback chain failed.", len(candidates))
    return (
        "All AI models are currently busy. "
        "Please try again in a moment or contact support directly."
    )


# ── Streaming public interface ────────────────────────────────────────────────

async def stream_support_agent(
    customer_id: str,
    message: str,
) -> AsyncGenerator[dict, None]:
    """
    Stream real-time events from the ReAct agent using ``astream_events`` v2.

    Provider fallback order mirrors :func:`run_support_agent`.

    Yields
    ------
    ``{"type": "tool_start", "tool": <name>, "label": <friendly text>}``
        Emitted when the agent invokes a tool.
    ``{"type": "tool_end", "tool": <name>}``
        Emitted when a tool call completes.
    ``{"type": "token", "content": <chunk>}``
        Individual LLM output token (final response only, not tool-selection).
    ``{"type": "done", "content": <full_text>}``
        Complete accumulated response — use this as the canonical final value.
    ``{"type": "error", "message": <description>}``
        Unrecoverable failure.
    """
    user_input = f"[Customer ID: {customer_id}]\n\n{message}"

    candidates: list[tuple[str, object]] = []
    if GROQ_API_KEY:
        for model in GROQ_FALLBACK_MODELS:
            candidates.append((f"groq/{model}", lambda m=model: _build_agent_groq(m)))
    if OLLAMA_ENABLED:
        candidates.append((f"ollama/{OLLAMA_MODEL}", _build_agent_ollama))

    if not candidates:
        yield {"type": "error", "message": "No LLM provider configured."}
        return

    rate_limited_retry: list[tuple[float, str, object]] = []

    for idx, (label, build_fn) in enumerate(candidates):
        try:
            if idx > 0:
                logger.warning("Streaming fallback to provider '%s'", label)

            agent = build_fn()
            full_response = ""

            async for event in agent.astream_events(
                {"messages": [("human", user_input)]},
                version="v2",
            ):
                event_type: str = event.get("event", "")
                event_name: str = event.get("name", "")

                if event_type == "on_tool_start":
                    label_text = _TOOL_LABELS.get(event_name, f"⚙️ Running {event_name}…")
                    yield {"type": "tool_start", "tool": event_name, "label": label_text}

                elif event_type == "on_tool_end":
                    yield {"type": "tool_end", "tool": event_name}

                elif event_type == "on_chat_model_stream":
                    chunk = event["data"].get("chunk")
                    if chunk is None:
                        continue
                    content = chunk.content if isinstance(chunk.content, str) else ""
                    tool_call_chunks = getattr(chunk, "tool_call_chunks", [])
                    if content and not tool_call_chunks and not _RAW_TOOL_CALL_RE.search(content):
                        full_response += content
                        yield {"type": "token", "content": content}

            final = full_response.strip()
            yield {
                "type": "done",
                "content": final or "I'm sorry, I was unable to process your request. Please try again.",
            }
            if idx > 0:
                logger.info("Streaming request served by fallback provider '%s'", label)
            return

        except Exception as exc:  # noqa: BLE001
            retry_after = _extract_retry_after(exc) if _is_rate_limit_error(exc) else None
            if retry_after is not None:
                logger.warning(
                    "Streaming provider '%s' rate limited (retry in %.1fs) – trying next",
                    label, retry_after,
                )
                rate_limited_retry.append((retry_after, label, build_fn))
            else:
                logger.warning(
                    "Streaming provider '%s' failed (%s) – trying next provider", label, exc
                )

    # ── All candidates exhausted on first pass ────────────────────────────────
    # If some were only rate-limited, wait for the shortest window and retry once.
    if rate_limited_retry:
        max_wait = max(d for d, *_ in rate_limited_retry)
        wait_secs = min(max_wait + 2.0, _RATE_LIMIT_MAX_WAIT)
        logger.warning(
            "All streaming providers rate limited. Waiting %.1fs before retrying %d provider(s).",
            wait_secs, len(rate_limited_retry),
        )
        await asyncio.sleep(wait_secs)

        for _delay, label, build_fn in sorted(rate_limited_retry, key=lambda x: x[0]):
            try:
                logger.info("Streaming retry with rate-limited provider '%s'", label)
                agent = build_fn()
                full_response = ""

                async for event in agent.astream_events(
                    {"messages": [("human", user_input)]},
                    version="v2",
                ):
                    event_type = event.get("event", "")
                    event_name = event.get("name", "")

                    if event_type == "on_tool_start":
                        label_text = _TOOL_LABELS.get(event_name, f"⚙️ Running {event_name}…")
                        yield {"type": "tool_start", "tool": event_name, "label": label_text}
                    elif event_type == "on_tool_end":
                        yield {"type": "tool_end", "tool": event_name}
                    elif event_type == "on_chat_model_stream":
                        chunk = event["data"].get("chunk")
                        if chunk is None:
                            continue
                        content = chunk.content if isinstance(chunk.content, str) else ""
                        tool_call_chunks = getattr(chunk, "tool_call_chunks", [])
                        if content and not tool_call_chunks and not _RAW_TOOL_CALL_RE.search(content):
                            full_response += content
                            yield {"type": "token", "content": content}

                final = full_response.strip()
                yield {
                    "type": "done",
                    "content": final or "I'm sorry, I was unable to process your request. Please try again.",
                }
                logger.info("Streaming rate-limit retry succeeded with provider '%s'", label)
                return

            except Exception as exc:  # noqa: BLE001
                logger.warning("Streaming retry of provider '%s' also failed: %s", label, exc)

    logger.critical("All streaming providers in fallback chain failed.")
    yield {"type": "error", "message": "All AI models are currently busy. Please try again in a moment."}
    return

