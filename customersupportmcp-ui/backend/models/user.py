"""
User and PasswordResetToken SQLAlchemy models.

Table: users
  - Supports both local (email + hashed_password) and OAuth-only accounts.
  - ``hashed_password`` is NULL for pure social-login users.
  - ``oauth_provider`` / ``oauth_id`` pair identifies a social account.

Table: password_reset_tokens
  - Stores a SHA-256 hash of the one-time reset token (never the raw token).
  - Tokens expire and are single-use (used=True after first successful reset).
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID

from core.database import Base


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── User ───────────────────────────────────────────────────────────────────────

class User(Base):
    """Application user — local or OAuth-authenticated."""

    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    username = Column(String(64), unique=True, index=True, nullable=True)
    full_name = Column(String(200), nullable=True)

    # NULL for OAuth-only accounts
    hashed_password = Column(String(255), nullable=True)

    is_active = Column(Boolean, default=True, nullable=False)
    is_verified = Column(Boolean, default=False, nullable=False)

    # Social login fields
    oauth_provider = Column(String(32), nullable=True)   # "google" | "facebook"
    oauth_id = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        # Each social provider+id pair must be unique
        UniqueConstraint("oauth_provider", "oauth_id", name="uq_user_oauth"),
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"


# ── Password Reset Token ───────────────────────────────────────────────────────

class PasswordResetToken(Base):
    """Single-use password reset token (stores hash, not raw token)."""

    __tablename__ = "password_reset_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hex digest of the raw token sent to the user
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return f"<PasswordResetToken user_id={self.user_id} used={self.used}>"


# ── Email Verification Token ───────────────────────────────────────────────────

class EmailVerificationToken(Base):
    """Single-use email verification token (stores hash, not raw token)."""

    __tablename__ = "email_verification_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SHA-256 hex digest of the raw token sent to the user
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    used = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)

    def is_expired(self) -> bool:
        return datetime.now(timezone.utc) > self.expires_at

    def __repr__(self) -> str:
        return f"<EmailVerificationToken user_id={self.user_id} used={self.used}>"
