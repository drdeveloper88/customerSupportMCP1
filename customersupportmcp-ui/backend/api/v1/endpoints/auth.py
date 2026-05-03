"""
Authentication endpoints.

Routes
------
  POST   /api/v1/auth/token              Local email+password login → JWT
  POST   /api/v1/auth/register           New local-auth account
  POST   /api/v1/auth/logout             Revoke current JWT (server-side blocklist)
  GET    /api/v1/auth/me                 Current user info (requires JWT)
  PATCH  /api/v1/auth/me                 Update profile (requires JWT)
  GET    /api/v1/auth/verify-email       Consume email verification token
  POST   /api/v1/auth/resend-verification  Re-send verification email (requires JWT)
  POST   /api/v1/auth/change-password    Change password (requires JWT)
  POST   /api/v1/auth/forgot-password    Request password-reset email
  POST   /api/v1/auth/reset-password     Submit new password with reset token
  GET    /api/v1/auth/oauth/{provider}   Initiate Google / Facebook OAuth2 flow
  GET    /api/v1/auth/oauth/{provider}/callback  OAuth2 redirect callback

OWASP hardening
---------------
* Generic 401 messages — no user enumeration.
* Constant-time password comparison (via passlib bcrypt).
* Reset tokens stored as SHA-256 hashes; raw token travels only in email.
* OAuth state tokens stored in Redis (5 min TTL) to prevent CSRF.
* Rate limiting applied via slowapi (configured in main.py).
* All inputs validated and sanitised by Pydantic validators.
"""

import asyncio
import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from core.auth import revoke_token, verify_token
from core.config import (
    FACEBOOK_APP_ID,
    FACEBOOK_APP_SECRET,
    FRONTEND_URL,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_SECRET_KEY,
    OAUTH_REDIRECT_BASE_URL,
    RATE_LIMIT_AUTH,
    RATE_LIMIT_RESET,
    REDIS_URL,
)
from core.database import get_db
from core.limiter import limiter
from core.security import generate_token, hash_token
from services.auth_service import (
    authenticate_user,
    change_user_password,
    create_email_verification_token,
    create_password_reset_token,
    get_or_create_oauth_user,
    get_user_by_id,
    issue_token_for_user,
    register_user,
    reset_password,
    update_user_profile,
    verify_email_token,
)
from services.email_service import (
    send_password_reset_email,
    send_verification_email,
    send_welcome_email,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Auth"])

# ── Redis client (for OAuth CSRF state) ───────────────────────────────────────

_redis_client = None


def _get_redis():
    global _redis_client
    if _redis_client is None:
        try:
            import redis as redis_lib
            _redis_client = redis_lib.from_url(REDIS_URL, decode_responses=True)
        except Exception as exc:
            logger.warning("Redis unavailable, OAuth CSRF state skipped: %s", exc)
    return _redis_client


# ── Authlib OAuth2 setup ───────────────────────────────────────────────────────

_oauth = None


def _get_oauth():
    global _oauth
    if _oauth is not None:
        return _oauth
    try:
        from authlib.integrations.starlette_client import OAuth
        from starlette.config import Config as StarletteConfig
        cfg = StarletteConfig(environ={
            "GOOGLE_CLIENT_ID": GOOGLE_CLIENT_ID or "",
            "GOOGLE_CLIENT_SECRET": GOOGLE_CLIENT_SECRET or "",
            "FACEBOOK_CLIENT_ID": FACEBOOK_APP_ID or "",
            "FACEBOOK_CLIENT_SECRET": FACEBOOK_APP_SECRET or "",
        })
        _oauth = OAuth(cfg)
        if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
            _oauth.register(
                name="google",
                server_metadata_url=(
                    "https://accounts.google.com/.well-known/openid-configuration"
                ),
                client_kwargs={"scope": "openid email profile"},
            )
        if FACEBOOK_APP_ID and FACEBOOK_APP_SECRET:
            _oauth.register(
                name="facebook",
                api_base_url="https://graph.facebook.com/v19.0/",
                access_token_url="https://graph.facebook.com/v19.0/oauth/access_token",
                authorize_url="https://www.facebook.com/dialog/oauth",
                client_kwargs={"scope": "email public_profile"},
            )
    except ImportError:
        logger.warning("authlib not installed — OAuth endpoints disabled.")
    return _oauth


# ── Input validation helpers ───────────────────────────────────────────────────

_SAFE_RE = re.compile(r"^[^<>{}\[\]\\;]*$")
_STRONG_PASSWORD_RE = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*()\-_=+\[\]{};:'\",.<>/?\\|`~]).{8,}$"
)


def _safe(value: str) -> str:
    if not _SAFE_RE.match(value):
        raise ValueError("Input contains disallowed characters.")
    return value.strip()


# ── Schemas ────────────────────────────────────────────────────────────────────


class TokenRequest(BaseModel):
    email_or_username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("email_or_username", mode="before")
    @classmethod
    def sanitize_identifier(cls, v: str) -> str:
        return _safe(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=200)
    username: Optional[str] = Field(None, min_length=3, max_length=64)

    @field_validator("password", mode="before")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not _STRONG_PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be at least 8 characters and include uppercase, "
                "lowercase, a digit, and a special character."
            )
        return v

    @field_validator("full_name", mode="before")
    @classmethod
    def sanitize_full_name(cls, v: str) -> str:
        return _safe(v)

    @field_validator("username", mode="before")
    @classmethod
    def sanitize_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _safe(v)


class UserResponse(BaseModel):
    id: str
    email: str
    username: Optional[str]
    full_name: Optional[str]
    is_verified: bool
    oauth_provider: Optional[str]


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password", mode="before")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not _STRONG_PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be at least 8 characters and include uppercase, "
                "lowercase, a digit, and a special character."
            )
        return v


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("new_password", mode="before")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if not _STRONG_PASSWORD_RE.match(v):
            raise ValueError(
                "Password must be at least 8 characters and include uppercase, "
                "lowercase, a digit, and a special character."
            )
        return v


class ProfileUpdateRequest(BaseModel):
    full_name: Optional[str] = Field(None, min_length=1, max_length=200)
    username: Optional[str] = Field(None, min_length=3, max_length=64)

    @field_validator("full_name", mode="before")
    @classmethod
    def sanitize_full_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _safe(v)

    @field_validator("username", mode="before")
    @classmethod
    def sanitize_username(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        return _safe(v)


# ── Endpoints ──────────────────────────────────────────────────────────────────


@router.post(
    "/auth/token",
    response_model=TokenResponse,
    summary="Login with email/username and password",
    description=(
        "Authenticate and receive a signed JWT. "
        "Pass the token as `Authorization: Bearer <token>` on subsequent requests."
    ),
)
@limiter.limit(RATE_LIMIT_AUTH)
async def login(request: Request, body: TokenRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, body.email_or_username, body.password)
    token = issue_token_for_user(user)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new account",
)
@limiter.limit(RATE_LIMIT_AUTH)
async def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Create a new local-auth user account and return a JWT."""
    user = register_user(
        db,
        email=str(body.email),
        password=body.password,
        full_name=body.full_name,
        username=body.username,
    )
    # Send welcome + verification emails (fire-and-forget, won't block response)
    asyncio.ensure_future(send_welcome_email(user.email, user.full_name or ""))
    raw_verify_token = create_email_verification_token(db, user.id)
    asyncio.ensure_future(send_verification_email(user.email, raw_verify_token))

    token = issue_token_for_user(user)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=JWT_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/auth/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Logout and revoke the current JWT",
)
async def logout(request: Request):
    """Add the current JWT's JTI to a Redis blocklist, immediately invalidating it."""
    token = _extract_bearer(request)
    try:
        from jose import jwt as _jwt
        payload = _jwt.decode(
            token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},  # still revoke expired tokens gracefully
        )
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            from datetime import datetime, timezone as _tz
            ttl = max(0, int(exp - datetime.now(_tz.utc).timestamp()))
            revoke_token(jti, ttl + 60)  # +60s buffer
    except Exception:
        pass  # Even if decode fails, clear client-side token succeeds
    return None


@router.get(
    "/auth/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(request: Request, db: Session = Depends(get_db)) -> UserResponse:
    token = _extract_bearer(request)
    payload = verify_token(token)
    user = get_user_by_id(db, payload.get("sub"))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_verified=user.is_verified,
        oauth_provider=user.oauth_provider,
    )


@router.patch(
    "/auth/me",
    response_model=UserResponse,
    summary="Update current user profile (full name, username)",
)
async def update_me(
    request: Request, body: ProfileUpdateRequest, db: Session = Depends(get_db)
) -> UserResponse:
    token = _extract_bearer(request)
    payload = verify_token(token)
    user = update_user_profile(
        db,
        user_id=payload.get("sub"),
        full_name=body.full_name,
        username=body.username,
    )
    return UserResponse(
        id=str(user.id),
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        is_verified=user.is_verified,
        oauth_provider=user.oauth_provider,
    )


@router.get(
    "/auth/verify-email",
    summary="Verify email address using the token from the verification email",
)
async def verify_email(token: str, db: Session = Depends(get_db)):
    """Consume a single-use verification token and mark the user's email as verified."""
    user = verify_email_token(db, token)
    return {
        "detail": "Email verified successfully. You can now sign in.",
        "email": user.email,
    }


@router.post(
    "/auth/resend-verification",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Re-send the email verification link",
)
@limiter.limit(RATE_LIMIT_RESET)
async def resend_verification(
    request: Request, db: Session = Depends(get_db)
):
    """Generate and re-send a verification email for the current user.

    Always returns 202 to prevent user enumeration.
    """
    try:
        token = _extract_bearer(request)
        payload = verify_token(token)
        user = get_user_by_id(db, payload.get("sub"))
        if user and not user.is_verified:
            raw_verify_token = create_email_verification_token(db, user.id)
            asyncio.ensure_future(send_verification_email(user.email, raw_verify_token))
    except Exception:
        pass  # Never reveal success/failure
    return {"detail": "If your account is unverified, a new verification email has been sent."}


@router.post(
    "/auth/change-password",
    summary="Change password (requires current JWT)",
)
async def change_password(
    request: Request, body: ChangePasswordRequest, db: Session = Depends(get_db)
):
    """Change the authenticated user's password. Requires the current password."""
    token = _extract_bearer(request)
    payload = verify_token(token)
    change_user_password(
        db,
        user_id=payload.get("sub"),
        old_password=body.old_password,
        new_password=body.new_password,
    )
    return {"detail": "Password updated successfully."}


@router.post(
    "/auth/forgot-password",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Request a password reset email",
)
@limiter.limit(RATE_LIMIT_RESET)
async def forgot_password(request: Request, body: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Always returns 202 to prevent email enumeration."""
    raw_token = create_password_reset_token(db, str(body.email))
    if raw_token:
        asyncio.ensure_future(send_password_reset_email(str(body.email), raw_token))
    return {"detail": "If that email is registered you will receive a reset link shortly."}


@router.post(
    "/auth/reset-password",
    summary="Complete password reset",
)
@limiter.limit(RATE_LIMIT_RESET)
async def reset_password_endpoint(
    request: Request, body: ResetPasswordRequest, db: Session = Depends(get_db)
):
    reset_password(db, body.token, body.new_password)
    return {"detail": "Your password has been reset. You can now sign in."}


# ── OAuth2 social login ────────────────────────────────────────────────────────

_SUPPORTED_PROVIDERS = {"google", "facebook"}


@router.get(
    "/auth/providers",
    summary="Report which OAuth2 providers are configured on this server",
)
async def list_providers():
    """Returns a map of provider → enabled (bool) so the UI can hide unconfigured buttons."""
    return {
        "google": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET),
        "facebook": bool(FACEBOOK_APP_ID and FACEBOOK_APP_SECRET),
    }


@router.get(
    "/auth/oauth/{provider}",
    summary="Initiate OAuth2 social login (Google / Facebook)",
    include_in_schema=True,
)
async def oauth_initiate(provider: str, request: Request):
    """Redirect the browser to the OAuth2 provider authorization page."""
    provider = provider.lower()
    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}")

    oauth = _get_oauth()
    client = getattr(oauth, provider, None) if oauth else None
    if client is None:
        # Redirect gracefully — Login.jsx already displays oauth_error=not_configured
        return RedirectResponse(f"{FRONTEND_URL}/?oauth_error=not_configured")

    # Generate a CSRF state token and store its hash in Redis (5 min TTL)
    state = generate_token(24)
    r = _get_redis()
    if r:
        try:
            r.setex(f"oauth_state:{hash_token(state)}", 300, "1")
        except Exception as exc:
            logger.warning("Could not store OAuth state in Redis: %s", exc)

    callback_url = f"{OAUTH_REDIRECT_BASE_URL}/api/v1/auth/oauth/{provider}/callback"
    return await client.authorize_redirect(request, callback_url, state=state)


@router.get(
    "/auth/oauth/{provider}/callback",
    summary="OAuth2 provider callback handler",
    include_in_schema=True,
)
async def oauth_callback(
    provider: str, request: Request, db: Session = Depends(get_db)
):
    """Handle OAuth2 redirect: validate CSRF state, fetch user info, issue JWT.

    Returns a redirect to the frontend with the JWT in the URL hash fragment
    (hash fragments are never sent to servers and not stored in browser history).
    """
    provider = provider.lower()
    if provider not in _SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=400, detail="Unsupported provider.")

    # Validate CSRF state
    state = request.query_params.get("state", "")
    r = _get_redis()
    if r and state:
        state_key = f"oauth_state:{hash_token(state)}"
        try:
            if not r.get(state_key):
                logger.warning("OAuth CSRF check failed for provider=%s", provider)
                return RedirectResponse(f"{FRONTEND_URL}/?oauth_error=csrf_invalid")
            r.delete(state_key)
        except Exception as exc:
            logger.warning("Redis error during OAuth state check: %s", exc)

    oauth = _get_oauth()
    client = getattr(oauth, provider, None) if oauth else None
    if client is None:
        return RedirectResponse(f"{FRONTEND_URL}/?oauth_error=not_configured")

    try:
        token_data = await client.authorize_access_token(request)
    except Exception as exc:
        logger.error("OAuth token exchange failed for %s: %s", provider, exc)
        return RedirectResponse(f"{FRONTEND_URL}/?oauth_error=token_exchange_failed")

    user_info = await _fetch_oauth_user_info(provider, client, token_data)
    if not user_info or not user_info.get("email"):
        return RedirectResponse(f"{FRONTEND_URL}/?oauth_error=no_email")

    user = get_or_create_oauth_user(
        db,
        provider=provider,
        oauth_id=user_info["id"],
        email=user_info["email"],
        full_name=user_info.get("name"),
    )

    jwt_token = issue_token_for_user(user)
    # Deliver the token via hash fragment — never included in server logs
    return RedirectResponse(f"{FRONTEND_URL}/#oauth_token={jwt_token}")


# ── Internal helpers ───────────────────────────────────────────────────────────


async def _fetch_oauth_user_info(
    provider: str, client, token_data: dict
) -> Optional[dict]:
    try:
        if provider == "google":
            claims = token_data.get("userinfo") or {}
            if not claims:
                resp = await client.get(
                    "https://www.googleapis.com/oauth2/v3/userinfo",
                    token=token_data,
                )
                claims = resp.json()
            return {
                "id": claims.get("sub"),
                "email": claims.get("email"),
                "name": claims.get("name"),
            }
        elif provider == "facebook":
            resp = await client.get("me?fields=id,name,email", token=token_data)
            data = resp.json()
            return {
                "id": data.get("id"),
                "email": data.get("email"),
                "name": data.get("name"),
            }
    except Exception as exc:
        logger.error("Failed to fetch user info from %s: %s", provider, exc)
    return None


def _extract_bearer(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return auth[len("Bearer "):]
