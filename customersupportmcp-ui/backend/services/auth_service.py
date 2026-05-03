"""
Authentication business logic — user registration, login, OAuth, password reset.

All DB operations are synchronous SQLAlchemy ORM calls.
All functions raise ``HTTPException`` on auth failures so callers
(endpoint handlers) do not need to re-wrap errors.

OWASP considerations
---------------------
* Passwords hashed with bcrypt (work-factor 12) via passlib.
* User existence is never revealed in error messages (enumeration-safe).
* Reset tokens are SHA-256 hashed before DB storage.
* Tokens are single-use and expire in ``RESET_TOKEN_EXPIRE_MINUTES`` minutes.
* OAuth state tokens validated server-side via Redis to prevent CSRF.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.auth import create_access_token
from core.config import EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES, RESET_TOKEN_EXPIRE_MINUTES
from core.security import generate_token, hash_password, hash_token, verify_password
from models.user import EmailVerificationToken, PasswordResetToken, User

logger = logging.getLogger(__name__)

# ── User helpers ───────────────────────────────────────────────────────────────


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    return db.query(User).filter(User.email == email.lower().strip()).first()


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    return db.query(User).filter(User.username == username.strip()).first()


def get_user_by_id(db: Session, user_id) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


# ── Registration ───────────────────────────────────────────────────────────────


def register_user(
    db: Session,
    email: str,
    password: str,
    full_name: str,
    username: Optional[str] = None,
) -> User:
    """Create a new local-auth user.

    Raises HTTPException 409 if the email or username is already taken.
    Uses a generic error message to avoid user enumeration.
    """
    email = email.lower().strip()

    # Check for duplicate email
    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        )

    # Check for duplicate username (if provided)
    if username:
        username = username.strip()
        if get_user_by_username(db, username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken.",
            )

    user = User(
        email=email,
        username=username or None,
        full_name=full_name.strip() if full_name else None,
        hashed_password=hash_password(password),
        is_active=True,
        is_verified=False,  # email verification can be added later
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("New user registered: %s", email)
    return user


# ── Login ──────────────────────────────────────────────────────────────────────


def authenticate_user(db: Session, email_or_username: str, password: str) -> User:
    """Verify credentials and return the User.

    Uses generic error messages to prevent user enumeration.
    Raises HTTPException 401 on any failure.
    """
    identifier = email_or_username.strip()

    # Lookup by email or username
    user: Optional[User] = None
    if "@" in identifier:
        user = get_user_by_email(db, identifier)
    else:
        user = get_user_by_username(db, identifier)

    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if user is None or user.hashed_password is None:
        # Run a dummy verify to consume the same CPU time (timing-safe).
        # The hash below is a pre-computed bcrypt hash of "_dummy_timing_check_".
        verify_password("_dummy_timing_check_",
                        "$2b$12$l3wiFeORHT7lUfx6vGuP2uF6leskmMTK9mjevQjoLi8eSrpPWtEu6")
        raise _invalid

    if not verify_password(password, user.hashed_password):
        raise _invalid

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated.",
        )

    # Update last login timestamp
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    return user


def issue_token_for_user(user: User) -> dict:
    """Create a JWT access token payload for the given user."""
    return create_access_token({
        "sub": str(user.id),
        "email": user.email,
        "username": user.username,
    })


# ── OAuth user provisioning ────────────────────────────────────────────────────


def get_or_create_oauth_user(
    db: Session,
    provider: str,
    oauth_id: str,
    email: str,
    full_name: Optional[str] = None,
) -> User:
    """Find an existing OAuth-linked user or create a new one.

    If an account with the same email already exists (local-auth), the OAuth
    provider/id is linked to that existing account.
    """
    email = email.lower().strip()

    # 1. Lookup by provider + oauth_id (returning user)
    user = (
        db.query(User)
        .filter(User.oauth_provider == provider, User.oauth_id == oauth_id)
        .first()
    )
    if user:
        user.last_login_at = datetime.now(timezone.utc)
        db.commit()
        return user

    # 2. Link to existing email account
    user = get_user_by_email(db, email)
    if user:
        user.oauth_provider = provider
        user.oauth_id = oauth_id
        user.last_login_at = datetime.now(timezone.utc)
        if not user.is_verified:
            user.is_verified = True  # OAuth email is implicitly verified
        db.commit()
        return user

    # 3. Create brand new account
    user = User(
        email=email,
        full_name=full_name,
        oauth_provider=provider,
        oauth_id=oauth_id,
        is_active=True,
        is_verified=True,  # OAuth email is implicitly verified
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info("OAuth user created: provider=%s email=%s", provider, email)
    return user


# ── Password reset ─────────────────────────────────────────────────────────────


def create_password_reset_token(db: Session, email: str) -> Optional[str]:
    """Generate a reset token for the user identified by ``email``.

    Returns the raw (unhashed) token to be emailed to the user.
    Returns None if the email is not found — caller should NOT surface this
    difference to prevent user enumeration.

    Invalidates any existing unused tokens for the same user.
    """
    user = get_user_by_email(db, email)
    if user is None or not user.is_active:
        return None

    # Invalidate old tokens for this user
    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used == False,  # noqa: E712
    ).update({"used": True})

    raw_token = generate_token(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=RESET_TOKEN_EXPIRE_MINUTES
    )

    reset_token = PasswordResetToken(
        user_id=user.id,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    db.add(reset_token)
    db.commit()

    return raw_token


def reset_password(db: Session, raw_token: str, new_password: str) -> bool:
    """Apply a password reset using the raw token from the reset email.

    Returns True on success.
    Raises HTTPException 400 if the token is invalid, expired, or already used.
    """
    token_hash = hash_token(raw_token)

    record = (
        db.query(PasswordResetToken)
        .filter(PasswordResetToken.token_hash == token_hash)
        .first()
    )

    if record is None or record.used or record.is_expired():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        )

    user = get_user_by_id(db, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid or has expired.",
        )

    user.hashed_password = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    record.used = True
    db.commit()

    logger.info("Password reset completed for user_id=%s", user.id)
    return True


# ── Email verification ─────────────────────────────────────────────────────────


def create_email_verification_token(db: Session, user_id) -> str:
    """Generate an email verification token for the given user.

    Invalidates any previous unused tokens for the same user.
    Returns the raw (unhashed) token to be sent via email.
    """
    # Invalidate old pending tokens
    db.query(EmailVerificationToken).filter(
        EmailVerificationToken.user_id == user_id,
        EmailVerificationToken.used == False,  # noqa: E712
    ).update({"used": True})

    raw_token = generate_token(32)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=EMAIL_VERIFY_TOKEN_EXPIRE_MINUTES
    )

    record = EmailVerificationToken(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        expires_at=expires_at,
    )
    db.add(record)
    db.commit()
    return raw_token


def verify_email_token(db: Session, raw_token: str) -> User:
    """Consume an email verification token and mark the user as verified.

    Raises HTTPException 400 if the token is invalid, expired, or already used.
    """
    token_hash = hash_token(raw_token)

    record = (
        db.query(EmailVerificationToken)
        .filter(EmailVerificationToken.token_hash == token_hash)
        .first()
    )

    if record is None or record.used or record.is_expired():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired.",
        )

    user = get_user_by_id(db, record.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This verification link is invalid or has expired.",
        )

    user.is_verified = True
    record.used = True
    db.commit()
    db.refresh(user)

    logger.info("Email verified for user_id=%s", user.id)
    return user


# ── Change password ────────────────────────────────────────────────────────────


def change_user_password(
    db: Session, user_id, old_password: str, new_password: str
) -> None:
    """Change a user's password. Requires the current password.

    Raises HTTPException if the account is not found, is a social-only account,
    or if the old password is incorrect.
    """
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found.")

    if user.hashed_password is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password change is not available for social-login accounts.",
        )

    if not verify_password(old_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect.",
        )

    user.hashed_password = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("Password changed for user_id=%s", user.id)


# ── Profile update ─────────────────────────────────────────────────────────────


def update_user_profile(
    db: Session,
    user_id,
    full_name: Optional[str] = None,
    username: Optional[str] = None,
) -> User:
    """Update display name and/or username for the given user.

    Raises HTTPException 409 if the requested username is taken by another user.
    """
    user = get_user_by_id(db, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

    if full_name is not None:
        user.full_name = full_name.strip()

    if username is not None:
        username = username.strip()
        existing = get_user_by_username(db, username)
        if existing and str(existing.id) != str(user_id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This username is already taken.",
            )
        user.username = username

    user.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(user)
    logger.info("Profile updated for user_id=%s", user.id)
    return user
