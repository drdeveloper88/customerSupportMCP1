"""
JWT authentication helpers.

Token format
------------
  header   : {"alg": "HS256", "typ": "JWT"}
  payload  : {"sub": "<user_id>", "email": "...", "username": "...",
               "jti": "<uuid4>", "iat": <unix_ts>, "exp": <unix_ts>}

Usage
-----
  # Create
  token = create_access_token({"sub": "user-uuid"})

  # Verify (raises HTTPException 401 if invalid or revoked)
  payload = verify_token(token)

  # Logout / revoke
  revoke_token(payload["jti"], ttl_seconds)
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from jose import JWTError, jwt

from core.config import JWT_ALGORITHM, JWT_EXPIRE_MINUTES, JWT_SECRET_KEY, REDIS_URL

# ── Lazy Redis client (for token blocklist) ────────────────────────────────────

_redis_client = None


def _get_redis():
    """Return a Redis client, or None if unavailable (graceful degradation)."""
    global _redis_client
    if _redis_client is None:
        try:
            import redis as redis_lib
            _redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
            _redis_client.ping()
        except Exception:
            _redis_client = None
    return _redis_client


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Create a signed JWT access token.

    Args:
        data: Payload to encode (must include ``"sub"``).
        expires_delta: Custom TTL; defaults to ``JWT_EXPIRE_MINUTES`` from config.

    Returns:
        A signed JWT string.
    """
    payload = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta if expires_delta is not None else timedelta(minutes=JWT_EXPIRE_MINUTES)
    )
    payload["exp"] = expire
    payload["iat"] = now
    payload["jti"] = str(uuid.uuid4())  # unique token ID for revocation
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def revoke_token(jti: str, ttl_seconds: int) -> None:
    """Add the token JTI to the Redis blocklist with a TTL matching the token's remaining life.

    Silently skips if Redis is unavailable.
    """
    if not jti or ttl_seconds <= 0:
        return
    r = _get_redis()
    if r:
        try:
            r.setex(f"token_blocklist:{jti}", ttl_seconds, "1")
        except Exception:
            pass


def verify_token(token: str) -> dict:
    """Decode and verify a JWT access token.

    Args:
        token: Encoded JWT string (without ``"Bearer "`` prefix).

    Returns:
        Decoded payload dict.

    Raises:
        HTTPException(401): Token is missing, expired, invalid, or revoked.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        subject: str | None = payload.get("sub")
        if subject is None:
            raise credentials_exception

        # Check token revocation blocklist
        jti: str | None = payload.get("jti")
        if jti:
            r = _get_redis()
            if r:
                try:
                    if r.get(f"token_blocklist:{jti}"):
                        raise HTTPException(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token has been revoked",
                            headers={"WWW-Authenticate": "Bearer"},
                        )
                except HTTPException:
                    raise
                except Exception:
                    pass  # Redis error — fail open (graceful degradation)

        return payload
    except JWTError:
        raise credentials_exception

