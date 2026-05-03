"""
SQLAlchemy database engine, session factory, and base class.

All models import ``Base`` from this module and register themselves
via their import.  ``init_db()`` is called once at application startup
to create any tables that do not yet exist (idempotent).

Connection pool settings are conservative to fit a small container:
  - pool_size=5, max_overflow=10
  - pool_pre_ping=True  → validates connections before checkout
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from core.config import DATABASE_URL


# ── Engine ─────────────────────────────────────────────────────────────────────

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Declarative base ───────────────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ─────────────────────────────────────────────────────────

def get_db():
    """Yield a SQLAlchemy session, closing it after the request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ── Schema bootstrap ───────────────────────────────────────────────────────────

def init_db() -> None:
    """Create all tables that do not yet exist.

    Import the models here so SQLAlchemy registers them before
    ``create_all`` is called.  This is safe to call repeatedly.
    """
    # side-effect: registers models with metadata
    import models.user  # noqa: F401

    Base.metadata.create_all(bind=engine)
