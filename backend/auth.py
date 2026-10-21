"""Dashboard authentication.

A single operator password protects the whole dashboard. Nothing is stored in
plain text: the password is kept as a PBKDF2-HMAC-SHA256 digest with a random
salt, and the browser holds a signed, expiring token in an HttpOnly cookie.

State lives in the local SQLite ``app_meta`` table so there is no extra file to
manage and the value travels with the installation.

Public API
----------
- :func:`is_configured`   - a password has been set
- :func:`set_password`    - create or replace the password
- :func:`verify_password` - constant-time check with lockout after N failures
- :func:`issue_token`     - signed token for the cookie
- :func:`token_is_valid`  - verify signature and expiry
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from typing import Any, Dict, Optional, Tuple

import database

logger = logging.getLogger(__name__)

COOKIE_NAME = "reposter_auth"
TOKEN_TTL_SECONDS = 12 * 60 * 60  # 12 hours
PBKDF2_ITERATIONS = 200_000
MIN_PASSWORD_LENGTH = 6
MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 60

_META_HASH = "dashboard_password_hash"
_META_SECRET = "dashboard_token_secret"
_META_ENABLED = "dashboard_auth_enabled"

# Very small in-process throttle: this is a single-operator local dashboard.
_failures: Dict[str, Any] = {"count": 0, "until": 0.0}


# ----------------------------------------------------------------------
# Storage
# ----------------------------------------------------------------------
async def is_configured() -> bool:
    """Return True when a dashboard password has been stored."""
    value = await database.get_meta(_META_HASH)
    return bool(value)


async def is_enabled() -> bool:
    """Return True when the lock screen is active.

    The gate is off only when the operator explicitly disabled it *and* a
    password exists (there is nothing to unlock without a password).
    """
    if not await is_configured():
        return False
    flag = await database.get_meta(_META_ENABLED)
    return flag != "0"


async def set_enabled(enabled: bool) -> None:
    """Turn the lock screen on or off without touching the password."""
    await database.set_meta(_META_ENABLED, "1" if enabled else "0")
    logger.info("Dashboard lock %s", "enabled" if enabled else "disabled")


async def disable() -> None:
    """Remove the dashboard password and the signing secret.

    With no password stored the gate stays open until a new one is created.
    """
    await database.set_meta(_META_HASH, "")
    await database.set_meta(_META_SECRET, secrets.token_hex(32))
    await database.set_meta(_META_ENABLED, "0")
    _failures["count"] = 0
    _failures["until"] = 0.0
    logger.info("Dashboard password removed; lock disabled")


async def _secret() -> str:
    """Return the token signing secret, creating it on first use."""
    value = await database.get_meta(_META_SECRET)
    if value:
        return value
    value = secrets.token_hex(32)
    await database.set_meta(_META_SECRET, value)
    return value


# ----------------------------------------------------------------------
# Password hashing
# ----------------------------------------------------------------------
def _hash(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def _encode(password: str) -> str:
    salt = os.urandom(16)
    digest = _hash(password, salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def _matches(password: str, encoded: str) -> bool:
    try:
        scheme, iterations, salt_hex, digest_hex = encoded.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        expected = bytes.fromhex(digest_hex)
        actual = _hash(password, bytes.fromhex(salt_hex), int(iterations))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def password_length_ok(password: str) -> bool:
    return len((password or "").strip()) >= MIN_PASSWORD_LENGTH


async def set_password(password: str) -> None:
    """Create or replace the dashboard password and revoke old sessions."""
    await database.set_meta(_META_HASH, _encode(password))
    # Rotating the signing secret invalidates every previously issued cookie.
    await database.set_meta(_META_SECRET, secrets.token_hex(32))
    await database.set_meta(_META_ENABLED, "1")
    _failures["count"] = 0
    _failures["until"] = 0.0
    logger.info("Dashboard password updated")


async def change_password(current: str, new_password: str) -> Tuple[bool, str]:
    """Change the password after verifying the current one."""
    ok, reason = await verify_password(current)
    if not ok:
        return False, reason
    if not password_length_ok(new_password):
        return False, "too_short"
    await set_password(new_password)
    return True, "ok"


# ----------------------------------------------------------------------
# Verification with a simple lockout
# ----------------------------------------------------------------------
def _locked_for() -> float:
    remaining = _failures["until"] - time.monotonic()
    return remaining if remaining > 0 else 0.0


async def verify_password(password: str) -> Tuple[bool, str]:
    """Check a password, returning ``(ok, reason)``.

    ``reason`` is one of ``ok``, ``not_configured``, ``locked``, ``invalid``.
    """
    if _locked_for() > 0:
        return False, "locked"

    encoded = await database.get_meta(_META_HASH)
    if not encoded:
        return False, "not_configured"

    if _matches(password or "", encoded):
        _failures["count"] = 0
        _failures["until"] = 0.0
        return True, "ok"

    _failures["count"] += 1
    if _failures["count"] >= MAX_ATTEMPTS:
        _failures["until"] = time.monotonic() + LOCKOUT_SECONDS
        _failures["count"] = 0
        logger.warning("Dashboard login locked for %ss after repeated failures", LOCKOUT_SECONDS)
        return False, "locked"
    return False, "invalid"


def lockout_remaining() -> int:
    return int(_locked_for() + 0.999)


# ----------------------------------------------------------------------
# Session tokens
# ----------------------------------------------------------------------
async def issue_token() -> str:
    """Return a signed token holding the expiry timestamp."""
    expires = int(time.time()) + TOKEN_TTL_SECONDS
    secret = await _secret()
    signature = hmac.new(secret.encode(), str(expires).encode(), hashlib.sha256).hexdigest()
    return f"{expires}.{signature}"


async def token_is_valid(token: Optional[str]) -> bool:
    """Verify a cookie value: signature first, then expiry."""
    if not token or "." not in token:
        return False
    expires_raw, signature = token.split(".", 1)
    try:
        expires = int(expires_raw)
    except ValueError:
        return False
    secret = await _secret()
    expected = hmac.new(secret.encode(), expires_raw.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        return False
    return expires > int(time.time())


async def state(token: Optional[str]) -> Dict[str, Any]:
    """Snapshot used by the dashboard gate."""
    configured = await is_configured()
    enabled = await is_enabled()
    # With the gate off (no password, or explicitly disabled) the dashboard is open.
    authenticated = (not enabled) or (configured and await token_is_valid(token))
    return {
        "configured": configured,
        "enabled": enabled,
        "authenticated": authenticated,
        "min_length": MIN_PASSWORD_LENGTH,
        "locked_for": lockout_remaining(),
    }
