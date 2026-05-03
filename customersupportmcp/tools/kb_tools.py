"""
Knowledge-base / FAQ search tools.

Search strategy
---------------
1. Semantic RAG search (ChromaDB + sentence-transformers)  — primary
   Understands meaning, handles synonyms, paraphrases, typos.
2. Keyword matching                                        — fallback
   Used automatically when chromadb / sentence-transformers are not
   installed, so the server still works without the optional deps.
"""

import json
import logging
import os

from langchain_core.tools import tool

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_KB_FILE  = os.path.join(_DATA_DIR, "knowledge_base.json")

# Module-level JSON cache (keyword path only)
_KB_CACHE: list[dict] | None = None

# ── RAG availability check ───────────────────────────────────────────────────

try:
    from data.rag_store import semantic_kb_search as _semantic_search
    _RAG_AVAILABLE = True
    logger.debug("RAG semantic KB search enabled.")
except ImportError:
    _RAG_AVAILABLE = False
    logger.warning(
        "chromadb / sentence-transformers not installed. "
        "Falling back to keyword-based KB search.  "
        "Run: pip install chromadb sentence-transformers"
    )


# ── Keyword search (fallback) ────────────────────────────────────────────────

def _load_kb() -> list[dict]:
    global _KB_CACHE
    if _KB_CACHE is None:
        with open(_KB_FILE, encoding="utf-8") as fh:
            _KB_CACHE = json.load(fh)
    return _KB_CACHE


def _invalidate_kb_cache() -> None:
    """Force a JSON reload on the next :func:`_load_kb` call."""
    global _KB_CACHE
    _KB_CACHE = None


def _score(article: dict, words: set[str]) -> int:
    score   = 0
    kw_set  = {k.lower() for k in article.get("keywords", [])}
    q_lower = article["question"].lower()
    a_lower = article["answer"].lower()
    c_lower = article["category"].lower()
    for word in words:
        if len(word) < 3:
            continue
        if word in kw_set:   score += 4
        if word in q_lower:  score += 3
        if word in c_lower:  score += 2
        if word in a_lower:  score += 1
    return score


def _keyword_search(query: str, max_results: int = 3) -> list[dict]:
    words  = set(query.lower().split())
    scored = [(a, _score(a, words)) for a in _load_kb()]
    scored = [(a, s) for a, s in scored if s > 0]
    scored.sort(key=lambda x: x[1], reverse=True)
    return [a for a, _ in scored[:max_results]]


# ── Unified search: RAG-first, keyword fallback ───────────────────────────────

def _search(query: str, max_results: int = 3) -> list[dict]:
    if _RAG_AVAILABLE:
        try:
            results = _semantic_search(query, k=max_results)
            if results:
                return results
            logger.debug(
                "Semantic search returned 0 results for %r — trying keyword fallback.",
                query,
            )
        except Exception as exc:
            logger.warning(
                "Semantic search raised an error (%s) — falling back to keyword search.",
                exc,
            )
    return _keyword_search(query, max_results)


# ── LangChain tool (used by the LangGraph agent) ─────────────────────────────

@tool
def search_knowledge_base(query: str) -> str:
    """Search the FAQ / knowledge base for answers to common customer questions.

    Uses semantic (meaning-based) search so it understands natural language,
    synonyms, and paraphrased questions — not just exact keyword matches.

    Always use this tool first before creating a support ticket, in case the
    question has a self-service answer.

    Args:
        query: The customer's question or a short description of their issue.
    """
    results = _search(query)
    if not results:
        return (
            "No relevant FAQ articles found for that query. "
            "Consider creating a support ticket for further assistance."
        )

    parts = []
    for r in results:
        score_tag = (
            f" — relevance {r['similarity_score']:.0%}"
            if "similarity_score" in r
            else ""
        )
        parts.append(
            f"[{r['category']}]{score_tag}\n"
            f"Q: {r['question']}\n"
            f"A: {r['answer']}"
        )

    return "\n\n---\n\n".join(parts)


# ── Public backward-compat alias ─────────────────────────────────────────────
# Some callers (main.py, support_service.py, tests) import search_kb directly.
# Expose the unified RAG-first search under that name so no other file changes.
search_kb = _search
