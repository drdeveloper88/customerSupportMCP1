"""
Cryptographic helpers: password hashing, secure token generation.

Passwords
---------
Uses bcrypt directly (work-factor 12) with SHA-256 pre-hashing so passwords
longer than bcrypt's 72-byte limit are handled correctly.
Never store raw passwords.

Tokens
------
``generate_token()``  → URL-safe random string (for reset links / OAuth state)
``hash_token()``      → SHA-256 hex digest for DB storage (one-way)
"""

import hashlib
import secrets

import bcrypt

# ── Password hashing ───────────────────────────────────────────────────────────

_BCRYPT_ROUNDS = 12


def _prehash(plain: str) -> bytes:
    """SHA-256 hex-digest of the password encoded as UTF-8 bytes.

    Keeps the input to bcrypt at exactly 64 ASCII bytes so it always falls
    within bcrypt's 72-byte limit, regardless of the original password length.
    """
    return hashlib.sha256(plain.encode("utf-8")).hexdigest().encode("ascii")


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of ``plain`` (bcrypt work-factor 12)."""
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if ``plain`` matches the bcrypt ``hashed`` value."""
    try:
        return bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))
    except Exception:
        return False


# ── Secure token generation ────────────────────────────────────────────────────

def generate_token(nbytes: int = 32) -> str:
    """Return a URL-safe cryptographically random token string.

    The raw token is sent to the user (e.g., in a reset-link URL).
    Always store ``hash_token(token)`` in the database, never the raw value.
    """
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of ``token`` for DB storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
