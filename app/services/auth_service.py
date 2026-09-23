"""Authentication and per-user session service.

Production-grade but dependency-free: passwords are salted PBKDF2-HMAC-SHA256
hashes and sessions are opaque bearer tokens stored server-side. Every request
that mutates or reads user data carries an ``Authorization: Bearer <token>``
header; the token maps to a single user, and that user's ``session_id`` is the
scope used for chat history and long-term memory. This gives real user
separation without trusting any client-supplied session identifier.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import get_connection

PBKDF2_ITERATIONS = 200_000
SALT_BYTES = 16
TOKEN_BYTES = 32


def _hash_password(password: str, salt: bytes) -> str:
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS
    )
    return digest.hex()


def _verify_password(password: str, salt: bytes, expected_hash: str) -> bool:
    return hmac.compare_digest(
        _hash_password(password, salt), expected_hash
    )


def register_user(username: str, password: str) -> dict:
    """Create a new account. Returns the user record or raises ValueError."""
    username = (username or "").strip()
    if len(username) < 3:
        raise ValueError("Username must be at least 3 characters.")
    if len(password) < 8:
        raise ValueError("Password must be at least 8 characters.")

    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE lower(username) = lower(?)",
            (username,),
        ).fetchone()
        if existing:
            raise ValueError("That username is already taken.")

        salt = secrets.token_bytes(SALT_BYTES)
        password_hash = _hash_password(password, salt)
        row = conn.execute(
            "INSERT INTO users (username, password_hash, salt) "
            "VALUES (?, ?, ?) RETURNING id",
            (username, password_hash, salt.hex()),
        ).fetchone()
        conn.commit()
        return {"id": row["id"], "username": username}
    finally:
        conn.close()


def authenticate(username: str, password: str) -> str | None:
    """Return a fresh bearer token on success, else ``None``."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, password_hash, salt FROM users "
            "WHERE lower(username) = lower(?)",
            ((username or "").strip(),),
        ).fetchone()
        if not row or not _verify_password(password, bytes.fromhex(row["salt"]), row["password_hash"]):
            return None

        token = secrets.token_hex(TOKEN_BYTES)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=settings.TOKEN_TTL_MINUTES)
        conn.execute(
            "INSERT INTO auth_sessions (token, user_id, created_at, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (token, row["id"], now.isoformat(), expires_at.isoformat()),
        )
        conn.commit()
        return token
    finally:
        conn.close()


def resolve_user(token: str) -> dict | None:
    """Resolve a bearer token to ``{user_id, username, session_id}`` or ``None``."""
    if not token:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT u.id AS user_id, u.username, s.expires_at
            FROM auth_sessions s
            JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            return None

        # Reject expired sessions. Rows created before expiry existed have a
        # NULL expires_at and are accepted (graceful upgrade path). The column
        # comes back as a datetime (PostgreSQL TIMESTAMPTZ) or, on older rows,
        # an ISO string — both are normalized here.
        raw_expiry = row["expires_at"]
        if raw_expiry is not None:
            expiry = raw_expiry
            if isinstance(expiry, str):
                try:
                    expiry = datetime.fromisoformat(expiry)
                except ValueError:
                    expiry = None
            if expiry is not None:
                if expiry.tzinfo is None:
                    expiry = expiry.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) >= expiry:
                    conn.execute(
                        "DELETE FROM auth_sessions WHERE token = ?", (token,)
                    )
                    conn.commit()
                    return None

        return {
            "user_id": row["user_id"],
            "username": row["username"],
            "session_id": f"user:{row['user_id']}",
        }
    finally:
        conn.close()


def revoke_token(token: str) -> None:
    """Remove a session token (logout)."""
    if not token:
        return
    conn = get_connection()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE token = ?", (token,))
        conn.commit()
    finally:
        conn.close()


def username_for_user_id(user_id: int | None) -> str | None:
    """Look up a username from its numeric id (for the action policy gate)."""
    if user_id is None:
        return None
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT username FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["username"] if row else None
    finally:
        conn.close()
