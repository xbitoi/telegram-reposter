"""Interactive Telethon user-account login driven from the dashboard.

Why this exists
---------------
A Telegram bot can only read a channel it administers. To read an arbitrary
source channel the reposter uses a real *user* account over MTProto. That
account must sign in once (phone number + login code, plus the 2FA password if
enabled) so Telethon persists a session file. Afterwards the reposter starts
with no prompt.

This module keeps a single Telethon client alive across the login steps so the
phone -> code -> password flow can be driven from the browser:

    start(phone)      -> sends the login code, remembers phone_code_hash
    submit_code(code) -> signs in, or reports that 2FA is required
    submit_password() -> finishes 2FA sign-in
    status()          -> a JSON-safe snapshot the dashboard can render

The session file is written next to ``.env`` (the backend directory when the
app is launched via ``start.bat``), which is exactly where
``telegram_client.TelegramReposter`` looks for it.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

import errors as error_catalog

logger = logging.getLogger(__name__)

# Where the session file lives: beside .env, never the current cwd.
_SESSION_DIR = Path(error_catalog.__file__).resolve().parent


def _session_dir(cfg_path: Optional[Path] = None) -> Path:
    """Directory that holds the .session file (next to .env)."""
    if cfg_path is not None:
        return Path(cfg_path).resolve().parent
    try:
        import config as config_module

        path = getattr(config_module.config, "path", None)
        if path:
            return Path(path).resolve().parent
    except Exception:  # noqa: BLE001 - fall back to backend dir
        pass
    return _SESSION_DIR


class LoginSession:
    """A single, resumable interactive login against Telegram."""

    def __init__(self) -> None:
        self._client: Optional[TelegramClient] = None
        self._lock = asyncio.Lock()

        # State surfaced to the dashboard.
        self.step: str = "idle"  # idle | code_sent | password_needed | authorized
        self.phone: Optional[str] = None
        self.phone_code_hash: Optional[str] = None
        self.user: Optional[Dict[str, Any]] = None
        self.last_error: Optional[Dict[str, Any]] = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _session_name(self) -> str:
        try:
            import config as config_module

            return config_module.config.get("session_name", "reposter_session")
        except Exception:  # noqa: BLE001
            return "reposter_session"

    def _session_path(self) -> str:
        try:
            import config as config_module

            cfg_path = getattr(config_module.config, "path", None)
        except Exception:  # noqa: BLE001
            cfg_path = None
        return str(_session_dir(cfg_path) / self._session_name())

    def _auth_ids(self) -> tuple[Optional[int], Optional[str]]:
        try:
            import config as config_module

            return (
                config_module.config.get("api_id"),
                config_module.config.get("api_hash"),
            )
        except Exception:  # noqa: BLE001
            return (None, None)

    async def _ensure_client(self) -> TelegramClient:
        api_id, api_hash = self._auth_ids()
        if not api_id or not api_hash:
            raise RuntimeError("api_id/api_hash are not configured")
        if self._client is None:
            self._client = TelegramClient(self._session_path(), int(api_id), str(api_hash))
        if not self._client.is_connected():
            await self._client.connect()
        return self._client

    async def _release_client(self) -> None:
        """Disconnect without logging out so the .session file is unlocked.

        The reposter opens the *same* session file with its own client; if we
        keep ours connected the SQLite file stays locked and starting the
        reposter fails with ``database is locked``. Signing in only persists the
        session to disk, so once we are authorized our client is disposable.
        """
        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def _already_authorized(self, client: TelegramClient) -> bool:
        try:
            return bool(await client.is_user_authorized())
        except Exception:  # noqa: BLE001
            return False

    @staticmethod
    def _user_dict(me: Any) -> Dict[str, Any]:
        if me is None:
            return {}
        full = " ".join(x for x in [getattr(me, "first_name", None),
                                    getattr(me, "last_name", None)] if x)
        return {
            "id": getattr(me, "id", None),
            "name": full or None,
            "username": getattr(me, "username", None),
            "phone": getattr(me, "phone", None),
        }

    def status(self) -> Dict[str, Any]:
        """JSON-safe snapshot for the dashboard (also used on reload)."""
        return {
            "step": self.step,
            "phone": self.phone,
            "user": self.user,
            "authorized": self.step == "authorized",
            "session_path": self._session_path(),
            "error": self.last_error,
        }

    def _clear_error(self) -> None:
        self.last_error = None

    def _fail(self, code: str, detail: Optional[str] = None, lang: str = "en") -> Dict[str, Any]:
        self.last_error = error_catalog.build_error(code, lang=lang, detail=detail)
        return self.last_error

    # ------------------------------------------------------------------
    # Public flow
    # ------------------------------------------------------------------
    async def refresh(self, lang: str = "en") -> Dict[str, Any]:
        """Re-check whether a session file already authorises the account."""
        async with self._lock:
            try:
                client = await self._ensure_client()
                if await self._already_authorized(client):
                    me = await client.get_me()
                    self.user = self._user_dict(me)
                    self.step = "authorized"
                    self.phone = self.user.get("phone") or self.phone
                    self._clear_error()
                    await self._release_client()
                elif self.step == "authorized":
                    # Session disappeared; reset.
                    self.step = "idle"
                    self.user = None
            except Exception as exc:  # noqa: BLE001
                logger.warning("login refresh failed: %s", exc)
                self._fail(error_catalog.classify(str(exc)), str(exc), lang)
            return self.status()

    async def start(self, phone: str, lang: str = "en") -> Dict[str, Any]:
        """Send the login code to ``phone``; remember the code hash."""
        async with self._lock:
            self._clear_error()
            phone = (phone or "").strip()
            if not phone:
                return {"ok": False, "status": self.status(),
                        "error": self._fail("LOGIN_PHONE_REQUIRED", lang=lang)}

            try:
                client = await self._ensure_client()
                if await self._already_authorized(client):
                    me = await client.get_me()
                    self.user = self._user_dict(me)
                    self.step = "authorized"
                    self.phone = self.user.get("phone") or phone
                    await self._release_client()
                    return {"ok": True, "status": self.status()}

                sent = await client.send_code_request(phone)
                self.phone = phone
                self.phone_code_hash = sent.phone_code_hash
                self.step = "code_sent"
                return {"ok": True, "status": self.status(),
                        "message": "code sent"}
            except PhoneNumberInvalidError as exc:
                err = self._fail("LOGIN_PHONE_INVALID", str(exc), lang)
                return {"ok": False, "status": self.status(), "error": err}
            except FloodWaitError as exc:
                err = self._fail("FLOOD_WAIT", f"wait {getattr(exc, 'seconds', '?')}s", lang)
                return {"ok": False, "status": self.status(), "error": err}
            except Exception as exc:  # noqa: BLE001
                err = self._fail(error_catalog.classify(str(exc)), str(exc), lang)
                return {"ok": False, "status": self.status(), "error": err}

    async def submit_code(self, code: str, lang: str = "en") -> Dict[str, Any]:
        """Sign in with the login code; report if 2FA is required."""
        async with self._lock:
            self._clear_error()
            code = (code or "").strip()
            if not self.phone or not self.phone_code_hash:
                return {"ok": False, "status": self.status(),
                        "error": self._fail("LOGIN_NO_CODE_REQUEST", lang=lang)}
            if not code:
                return {"ok": False, "status": self.status(),
                        "error": self._fail("LOGIN_CODE_REQUIRED", lang=lang)}

            try:
                client = await self._ensure_client()
                await client.sign_in(
                    phone=self.phone,
                    code=code,
                    phone_code_hash=self.phone_code_hash,
                )
            except SessionPasswordNeededError:
                self.step = "password_needed"
                return {"ok": True, "status": self.status(),
                        "message": "password required"}
            except PhoneCodeInvalidError as exc:
                err = self._fail("LOGIN_CODE_INVALID", str(exc), lang)
                return {"ok": False, "status": self.status(), "error": err}
            except PhoneCodeExpiredError as exc:
                err = self._fail("LOGIN_CODE_EXPIRED", str(exc), lang)
                return {"ok": False, "status": self.status(), "error": err}
            except Exception as exc:  # noqa: BLE001
                err = self._fail(error_catalog.classify(str(exc)), str(exc), lang)
                return {"ok": False, "status": self.status(), "error": err}

            # Clean sign-in without 2FA.
            client = await self._ensure_client()
            me = await client.get_me()
            self.user = self._user_dict(me)
            self.step = "authorized"
            await self._release_client()
            return {"ok": True, "status": self.status(), "message": "authorized"}

    async def submit_password(self, password: str, lang: str = "en") -> Dict[str, Any]:
        """Finish 2FA sign-in with the account password."""
        async with self._lock:
            self._clear_error()
            if self.step != "password_needed":
                return {"ok": False, "status": self.status(),
                        "error": self._fail("LOGIN_NO_PASSWORD_NEEDED", lang=lang)}
            if not password:
                return {"ok": False, "status": self.status(),
                        "error": self._fail("LOGIN_PASSWORD_REQUIRED", lang=lang)}

            try:
                client = await self._ensure_client()
                await client.sign_in(password=password)
                me = await client.get_me()
                self.user = self._user_dict(me)
                self.step = "authorized"
                await self._release_client()
                return {"ok": True, "status": self.status(), "message": "authorized"}
            except Exception as exc:  # noqa: BLE001
                err = self._fail("LOGIN_PASSWORD_INVALID", str(exc), lang)
                return {"ok": False, "status": self.status(), "error": err}

    async def logout(self) -> Dict[str, Any]:
        """Sign out and delete the stored session (used before a re-login)."""
        async with self._lock:
            try:
                if self._client is not None:
                    try:
                        await self._client.log_out()
                    except Exception:  # noqa: BLE001 - already logged out
                        pass
                    try:
                        await self._client.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
                    self._client = None
            finally:
                self.step = "idle"
                self.phone = None
                self.phone_code_hash = None
                self.user = None
                self._clear_error()
            return self.status()

    async def disconnect(self) -> None:
        """Drop the client without logging out (keeps the session file)."""
        async with self._lock:
            if self._client is not None:
                try:
                    await self._client.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                self._client = None


# Module-level singleton the API endpoints drive.
login_session = LoginSession()
