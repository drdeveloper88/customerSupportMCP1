"""
Email sending service — password reset and account notifications.

Uses ``aiosmtplib`` for async SMTP delivery.

Development mode
----------------
If ``SMTP_HOST`` is empty or ``EMAIL_ENABLED`` is False, emails are
logged to the console instead of being sent.  This lets you develop
locally without a real mail server.

Configuration (via environment variables)
-----------------------------------------
  EMAIL_ENABLED       "true" / "false" (default: false if SMTP_HOST not set)
  SMTP_HOST           e.g. smtp.gmail.com
  SMTP_PORT           587 (STARTTLS) or 465 (SSL)
  SMTP_USER           sender address / auth username
  SMTP_PASSWORD       SMTP auth password (app password for Gmail)
  EMAIL_FROM          display "From" address (defaults to SMTP_USER)
  FRONTEND_URL        used to build reset links
"""

import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import aiosmtplib

from core.config import (
    EMAIL_ENABLED,
    EMAIL_FROM,
    FRONTEND_URL,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


# ── Internal send helper ───────────────────────────────────────────────────────


async def _send(to: str, subject: str, html_body: str) -> None:
    """Send a single HTML email.

    Falls back to console logging when SMTP is not configured.
    """
    if not EMAIL_ENABLED:
        logger.info(
            "[EMAIL DEV MODE] To: %s | Subject: %s\n%s",
            to,
            subject,
            html_body,
        )
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_FROM
    msg["To"] = to
    msg.attach(MIMEText(html_body, "html"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=(SMTP_PORT == 587),
            use_tls=(SMTP_PORT == 465),
        )
        logger.info("Email sent to %s | Subject: %s", to, subject)
    except Exception as exc:
        logger.error("Failed to send email to %s: %s", to, exc)
        # Do not re-raise — email failure must not break the auth flow


# ── Password reset email ───────────────────────────────────────────────────────


async def send_password_reset_email(to_email: str, raw_token: str) -> None:
    """Send the password reset link to ``to_email``."""
    reset_url = f"{FRONTEND_URL}/?reset_token={raw_token}"

    html = f"""
    <html>
      <body style="font-family:sans-serif;background:#0f172a;color:#f1f5f9;padding:2rem;">
        <div style="max-width:480px;margin:auto;background:#1e293b;border-radius:12px;padding:2rem;">
          <h2 style="color:#6366f1;margin-top:0;">Reset your password</h2>
          <p>You requested a password reset for your Customer Support account.</p>
          <p>Click the button below to set a new password. This link expires in
             <strong>30 minutes</strong> and can only be used once.</p>
          <a href="{reset_url}"
             style="display:inline-block;padding:0.75rem 1.5rem;background:#6366f1;
                    color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">
            Reset Password
          </a>
          <p style="margin-top:1.5rem;font-size:0.8rem;color:#94a3b8;">
            If you did not request this, you can safely ignore this email.<br>
            The link will expire automatically.
          </p>
          <hr style="border-color:#334155;">
          <p style="font-size:0.75rem;color:#64748b;">
            Or copy this URL into your browser:<br>
            <code style="word-break:break-all;">{reset_url}</code>
          </p>
        </div>
      </body>
    </html>
    """

    await _send(to_email, "Reset your Customer Support password", html)


# ── Welcome / verification email ──────────────────────────────────────────────


async def send_welcome_email(to_email: str, full_name: str) -> None:
    """Send a welcome email after successful registration."""
    html = f"""
    <html>
      <body style="font-family:sans-serif;background:#0f172a;color:#f1f5f9;padding:2rem;">
        <div style="max-width:480px;margin:auto;background:#1e293b;border-radius:12px;padding:2rem;">
          <h2 style="color:#6366f1;margin-top:0;">Welcome, {full_name or "there"}! 🎧</h2>
          <p>Your Customer Support account has been created successfully.</p>
          <a href="{FRONTEND_URL}"
             style="display:inline-block;padding:0.75rem 1.5rem;background:#6366f1;
                    color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">
            Go to Customer Support
          </a>
        </div>
      </body>
    </html>
    """

    await _send(to_email, "Welcome to Customer Support", html)


# ── Email verification ────────────────────────────────────────────────────────


async def send_verification_email(to_email: str, raw_token: str) -> None:
    """Send the email address verification link to ``to_email``."""
    verify_url = f"{FRONTEND_URL}/?verify_token={raw_token}"

    html = f"""
    <html>
      <body style="font-family:sans-serif;background:#0f172a;color:#f1f5f9;padding:2rem;">
        <div style="max-width:480px;margin:auto;background:#1e293b;border-radius:12px;padding:2rem;">
          <h2 style="color:#6366f1;margin-top:0;">Verify your email address</h2>
          <p>Thanks for registering with Customer Support! Please confirm your email
             address to get full access to your account.</p>
          <p>Click the button below — this link is valid for <strong>24 hours</strong>
             and can only be used once.</p>
          <a href="{verify_url}"
             style="display:inline-block;padding:0.75rem 1.5rem;background:#6366f1;
                    color:#fff;border-radius:8px;text-decoration:none;font-weight:600;">
            Verify Email Address
          </a>
          <p style="margin-top:1.5rem;font-size:0.8rem;color:#94a3b8;">
            If you did not create this account, you can safely ignore this email.
          </p>
          <hr style="border-color:#334155;">
          <p style="font-size:0.75rem;color:#64748b;">
            Or copy this URL into your browser:<br>
            <code style="word-break:break-all;">{verify_url}</code>
          </p>
        </div>
      </body>
    </html>
    """

    await _send(to_email, "Verify your Customer Support email address", html)
