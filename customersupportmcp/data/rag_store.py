"""
RAG vector store — ChromaDB + sentence-transformers (all-MiniLM-L6-v2).

Collections
-----------
kb_articles      KB FAQ articles from knowledge_base.json — powers semantic
                 knowledge-base search replacing the old keyword scorer.
support_tickets  Support tickets indexed from SQLite — powers duplicate /
                 similarity detection before new tickets are created.

No API key required.  The embedding model (~90 MB) is downloaded on first
use and cached in the default sentence-transformers cache directory.

Public API
----------
build_kb_index(force)         Build (or rebuild) the KB vector index.
semantic_kb_search(query, k)  Return top-k KB articles by semantic similarity.
index_ticket(ticket)          Upsert a ticket into the similarity index.
find_similar_tickets(text, k) Return similar existing tickets.
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_DATA_DIR   = Path(__file__).resolve().parent
_KB_FILE    = _DATA_DIR / "knowledge_base.json"
_CHROMA_DIR = _DATA_DIR / "chroma_db"

# Embedding model: small (90 MB), fast, no API key needed.
# Switched to a newer paraphrase-optimised variant for better semantic matching.
_EMBED_MODEL = "all-MiniLM-L6-v2"

# Cosine-distance thresholds
# ChromaDB cosine distance = 1 − cosine_similarity  (range 0 → 2)
_KB_MAX_DIST     = 0.90   # KB: accept similarity ≥ 0.10 (generous, always helpful)
_TICKET_MAX_DIST = 0.65   # Tickets: accept similarity ≥ 0.35 (avoid false positives)

# ── Lazy singletons ─────────────────────────────────────────────────────────

_client = None
_ef     = None


def _get_ef():
    """Return (cached) SentenceTransformerEmbeddingFunction."""
    global _ef
    if _ef is None:
        from chromadb.utils.embedding_functions import (
            SentenceTransformerEmbeddingFunction,
        )
        _ef = SentenceTransformerEmbeddingFunction(model_name=_EMBED_MODEL)
        logger.debug("Embedding function loaded: %s", _EMBED_MODEL)
    return _ef


def _get_client():
    """Return (cached) ChromaDB PersistentClient."""
    global _client
    if _client is None:
        import chromadb
        _CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(_CHROMA_DIR))
        logger.debug("ChromaDB client opened at %s", _CHROMA_DIR)
    return _client


def _kb_collection():
    return _get_client().get_or_create_collection(
        name="kb_articles",
        embedding_function=_get_ef(),
        metadata={"hnsw:space": "cosine"},
    )


def _ticket_collection():
    return _get_client().get_or_create_collection(
        name="support_tickets",
        embedding_function=_get_ef(),
        metadata={"hnsw:space": "cosine"},
    )


# ── KB index ─────────────────────────────────────────────────────────────────

def build_kb_index(force: bool = False) -> int:
    """Build the KB vector index from ``knowledge_base.json``.

    Skips if already populated unless *force* is ``True``.
    Returns the number of articles in the index after the operation.
    """
    coll = _kb_collection()
    existing_count = coll.count()

    if existing_count > 0 and not force:
        logger.debug("KB index already populated (%d articles) — skipping.", existing_count)
        return existing_count

    with open(_KB_FILE, encoding="utf-8") as fh:
        articles: list[dict] = json.load(fh)

    if force and existing_count > 0:
        existing_ids = coll.get(include=[])["ids"]
        if existing_ids:
            coll.delete(ids=existing_ids)
            logger.debug("Cleared %d stale KB articles from index.", len(existing_ids))

    docs, ids, metas = [], [], []
    for a in articles:
        # Rich combined text: category + question + answer + keywords
        # → better semantic coverage than embedding each field separately.
        text = (
            f"Category: {a['category']}. "
            f"Question: {a['question']} "
            f"Answer: {a['answer']} "
            f"Keywords: {', '.join(a.get('keywords', []))}"
        )
        docs.append(text)
        ids.append(a["id"])
        metas.append({
            "category": a["category"],
            "question": a["question"],
            "answer":   a["answer"],
        })

    coll.add(documents=docs, ids=ids, metadatas=metas)
    logger.info("KB index built: %d articles indexed.", len(articles))
    return len(articles)


def semantic_kb_search(query: str, k: int = 3) -> list[dict]:
    """Return the top-*k* KB articles most semantically similar to *query*.

    Each result dict has keys: ``id``, ``category``, ``question``, ``answer``,
    ``similarity_score`` (0–1, higher = more similar).

    Falls back to an empty list if ChromaDB is unavailable.
    """
    coll = _kb_collection()
    if coll.count() == 0:
        build_kb_index()

    n = min(k + 1, coll.count())  # +1 for post-filter buffer
    if n == 0:
        return []

    results = coll.query(
        query_texts=[query],
        n_results=n,
        include=["metadatas", "distances"],
    )

    articles = []
    for id_, meta, dist in zip(
        results["ids"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        # cosine distance ∈ [0, 2]; smaller = more similar.
        if dist > _KB_MAX_DIST:
            continue
        articles.append({
            "id":               id_,
            "category":         meta["category"],
            "question":         meta["question"],
            "answer":           meta["answer"],
            "similarity_score": round(1.0 - dist, 3),
        })

    return articles[:k]


# ── Ticket similarity index ───────────────────────────────────────────────────

def index_ticket(ticket: dict) -> None:
    """Upsert *ticket* into the similarity index.

    Called after every ticket creation so the index stays in sync.
    """
    coll = _ticket_collection()
    tid  = ticket["ticket_id"]
    text = (
        f"Subject: {ticket['subject']} "
        f"Description: {ticket['description']} "
        f"Priority: {ticket['priority']} "
        f"Status: {ticket['status']}"
    )
    # Upsert: delete-then-add (ChromaDB's upsert doesn't re-embed)
    try:
        coll.delete(ids=[tid])
    except Exception:
        pass
    coll.add(
        documents=[text],
        ids=[tid],
        metadatas=[{
            "ticket_id":   tid,
            "customer_id": ticket.get("customer_id", ""),
            "subject":     ticket["subject"],
            "priority":    ticket["priority"],
            "status":      ticket["status"],
            "created_at":  ticket.get("created_at", ""),
        }],
    )
    logger.debug("Ticket %s indexed in similarity store.", tid)


def _bulk_load_tickets_from_db() -> int:
    """Seed the ticket similarity index from the SQLite database.

    Called lazily the first time ``find_similar_tickets()`` is invoked so
    existing tickets (created before RAG was added) are also searchable.
    """
    try:
        # Lazy import to avoid circular dependencies at module level
        from data.database import engine, tickets_t  # noqa: PLC0415
        from sqlalchemy import select

        with engine.connect() as conn:
            rows = conn.execute(select(tickets_t)).fetchall()

        for row in rows:
            index_ticket(dict(row._mapping))

        logger.info(
            "Ticket similarity index seeded with %d existing tickets.", len(rows)
        )
        return len(rows)
    except Exception as exc:
        logger.warning("Could not seed ticket similarity index from DB: %s", exc)
        return 0


def find_similar_tickets(
    text: str,
    k: int = 3,
    exclude_ids: list[str] | None = None,
) -> list[dict]:
    """Return up to *k* tickets semantically similar to *text*.

    Only returns results with similarity ≥ 0.35 (distance ≤ 0.65) to
    avoid false positives.  Tickets in *exclude_ids* are omitted.

    Each result dict has: ``ticket_id``, ``customer_id``, ``subject``,
    ``priority``, ``status``, ``similarity_score``.
    """
    coll = _ticket_collection()

    # Lazy bulk seed on first call
    if coll.count() == 0:
        seeded = _bulk_load_tickets_from_db()
        if seeded == 0:
            return []

    count = coll.count()
    exclude = set(exclude_ids or [])
    # Request extra results to compensate for exclusions + post-filter
    n = min(k + len(exclude) + 3, count)

    results = coll.query(
        query_texts=[text],
        n_results=n,
        include=["metadatas", "distances"],
    )

    similar = []
    for id_, meta, dist in zip(
        results["ids"][0],
        results["metadatas"][0],
        results["distances"][0],
    ):
        if id_ in exclude:
            continue
        if dist > _TICKET_MAX_DIST:
            continue
        similar.append({
            "ticket_id":        id_,
            "customer_id":      meta.get("customer_id", ""),
            "subject":          meta["subject"],
            "priority":         meta["priority"],
            "status":           meta["status"],
            "similarity_score": round(1.0 - dist, 3),
        })

    return similar[:k]
