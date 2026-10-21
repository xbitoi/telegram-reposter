"""Telethon client wrapper that reposts messages between channels.

Architecture
------------
- A *user* Telethon client (``user_client``) connects with the user's session
  and listens for ``NewMessage`` events on the source channel.
- A *bot* Telethon client (``bot_client``) connects with ``bot_token`` and
  posts to the destination channel (it must be an admin there).

The two clients share the running asyncio loop so everything stays async. The
handler measures latency from the moment a message is received until the copy
completes, logs it to SQLite, and broadcasts it to WebSocket subscribers
through a callback registry.

All network work is retried up to ``max_attempts`` times with exponential
backoff, and every failure is recorded in the ``errors`` table.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional

from telethon import TelegramClient, events
from telethon.errors import (
    FloodWaitError,
    MessageNotModifiedError,
    RPCError,
    SlowModeWaitError,
)
from telethon.tl.types import Message

import database

logger = logging.getLogger(__name__)

# Callback signature: async fn(event_name: str, payload: dict) -> None
EventCallback = Callable[[str, Dict[str, Any]], Awaitable[None]]

MAX_TEXT_PREVIEW = 200


def _content_type(message: Message) -> str:
    """Classify a message into a coarse content type string."""
    if message.photo:
        return "photo"
    if message.video:
        return "video"
    if message.document:
        if message.document.mime_type and message.document.mime_type.startswith("video/"):
            return "video"
        if message.document.mime_type and message.document.mime_type.startswith("audio/"):
            return "audio"
        return "document"
    if message.audio:
        return "audio"
    if message.voice:
        return "voice"
    if message.video_note:
        return "video_note"
    if message.sticker:
        return "sticker"
    if message.gif:
        return "gif"
    if message.poll:
        return "poll"
    if message.geo:
        return "location"
    if message.contact:
        return "contact"
    if message.text:
        return "text"
    return "unknown"


def _text_preview(message: Message) -> Optional[str]:
    text = (message.text or "").strip()
    if not text:
        return None
    if len(text) > MAX_TEXT_PREVIEW:
        return text[:MAX_TEXT_PREVIEW] + "…"
    return text


def _entity_id(entity: Any) -> str:
    """Return a stable string identifier for a channel/peer."""
    if entity is None:
        return ""
    if isinstance(entity, (int,)):
        return str(entity)
    return str(getattr(entity, "id", entity))


def _media_extension(message: Message) -> str:
    """Best-effort file extension for a message's media.

    Telethon needs a real file name to detect the media kind on upload, so the
    temp file must carry a sensible extension.
    """
    file_info = getattr(message, "file", None)
    ext = getattr(file_info, "ext", None)
    if ext:
        return ext if ext.startswith(".") else "." + ext
    if message.photo:
        return ".jpg"
    if message.video or message.gif or message.video_note:
        return ".mp4"
    if message.voice:
        return ".ogg"
    if message.sticker:
        return ".webp"
    if message.audio:
        return ".mp3"
    document = message.document
    if document is not None and document.mime_type:
        guessed = mimetypes.guess_extension(document.mime_type)
        if guessed:
            return guessed
    return ".bin"


def bot_id_from_token(token: Optional[str]) -> Optional[int]:
    """Extract the bot id Telegram encodes before the colon of a bot token."""
    if not token or ":" not in token:
        return None
    head = token.split(":", 1)[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


def remove_session_files(path: str) -> None:
    """Delete a Telethon SQLite session and its journal/WAL companions."""
    for suffix in ("", "-journal", "-wal", "-shm"):
        try:
            os.remove(path + ".session" + suffix)
        except FileNotFoundError:
            pass
        except OSError:
            logger.debug("Could not remove %s.session%s", path, suffix)


class TelegramReposter:
    """Owns the Telethon clients and the reposting loop."""

    def __init__(
        self,
        api_id: int,
        api_hash: str,
        bot_token: str,
        session_name: str = "reposter_session",
        source_channel: Any = None,
        destination_channel: Any = None,
        repost_mode: str = "copy",
        delay_settings: Optional[Dict[str, Any]] = None,
        retry_settings: Optional[Dict[str, Any]] = None,
        base_dir: Optional[str] = None,
        source_channels: Optional[List[Any]] = None,
    ) -> None:
        self.api_id = api_id
        self.api_hash = api_hash
        self.bot_token = bot_token
        self.session_name = session_name
        self.base_dir = base_dir
        # ``source_channels`` is the list of channels to listen on (1..N). It is
        # the authoritative set; ``source_channel`` is the legacy single value
        # and is folded in first for backwards compatibility.
        self.source_channels: List[Any] = self._normalise_source_channels(
            source_channels, source_channel
        )
        self.source_channel = self.source_channels[0] if self.source_channels else None
        self.destination_channel = destination_channel
        # Copy is the only supported mode: forwarding from the source channel is
        # impossible for a bot that is not a member of it (Telegram rejects it
        # with ForwardMessagesRequest). Any other value coerces to "copy".
        self.repost_mode = "copy"
        self.delay_settings = delay_settings or {"enabled": False, "min_seconds": 0, "max_seconds": 0}
        self.retry_settings = retry_settings or {"max_attempts": 3, "backoff_seconds": 2}

        self.user_client: Optional[TelegramClient] = None
        self.bot_client: Optional[TelegramClient] = None
        self._running = False
        self._handler = None
        self._source_entity: Any = None
        # Every resolved source entity, keyed by the raw configured value, so an
        # incoming message can be attributed to the channel it came from.
        self._source_entities: List[Any] = []
        self._source_titles: List[str] = []
        self._callbacks: List[EventCallback] = []
        self._tasks: set = set()
        self._start_time: Optional[datetime] = None

        # Cached identity info, populated on start().
        self._user_info: Dict[str, Any] = {}
        self._bot_info: Dict[str, Any] = {}
        self._source_title: Optional[str] = None
        self._dest_title: Optional[str] = None

    @staticmethod
    def _normalise_source_channels(
        source_channels: Optional[List[Any]], source_channel: Any
    ) -> List[Any]:
        """Return a de-duplicated, non-empty list of source channels.

        Accepts a list (the new form) and/or a single legacy value, strips
        blanks and removes duplicates while keeping order.
        """
        candidates: List[Any] = []
        if isinstance(source_channels, (list, tuple)):
            candidates.extend(source_channels)
        elif source_channels:
            candidates.append(source_channels)
        if source_channel:
            candidates.append(source_channel)

        seen: set = set()
        result: List[Any] = []
        for item in candidates:
            if item is None:
                continue
            if isinstance(item, str):
                item = item.strip()
                if not item:
                    continue
            key = str(item)
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    # ------------------------------------------------------------------
    # Callback registry (used by the WebSocket layer)
    # ------------------------------------------------------------------
    def on_event(self, callback: EventCallback) -> None:
        """Register an async callback invoked on every repost event."""
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def off_event(self, callback: EventCallback) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)

    async def _emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        for cb in list(self._callbacks):
            try:
                await cb(event_name, payload)
            except Exception:  # noqa: BLE001 - a bad subscriber must not break reposting
                logger.exception("WebSocket callback %r failed", cb)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    async def start(self) -> None:
        """Connect both clients, register the handler and mark as running."""
        if self._running:
            logger.warning("TelegramReposter already running; ignoring start()")
            return

        if not self.api_id or not self.api_hash:
            raise RuntimeError("api_id/api_hash are not configured")
        if not self.bot_token:
            raise RuntimeError("bot_token is not configured")
        if not self.source_channels:
            raise RuntimeError("source_channel is not configured")
        if not self.destination_channel:
            raise RuntimeError("destination_channel is not configured")
        logger.info(
            "Starting TelegramReposter (mode=%s, sources=%d)",
            self.repost_mode,
            len(self.source_channels),
        )

        self.user_client = TelegramClient(
            self._session_path(self.session_name), self.api_id, self.api_hash
        )

        await self.user_client.connect()
        if not await self.user_client.is_user_authorized():
            await self.user_client.disconnect()
            raise RuntimeError(
                "User session is not authorized. Sign in the user account once "
                "(phone number + login code) to create the session file before "
                "starting the reposter."
            )

        # A bot authenticates with its token, not with is_user_authorized().
        # A cached bot session may belong to a *previous* bot: Telethon then
        # keeps the old identity and silently ignores the new token. Compare the
        # session's bot id with the id embedded in the token and re-login when
        # they differ, so changing the bot in the dashboard really takes effect.
        try:
            self.bot_client = await self._start_bot_client()
        except Exception as exc:  # noqa: BLE001 - surfaced as a clean error
            await self.user_client.disconnect()
            raise RuntimeError(
                "Bot token is invalid or the bot is not authorized. Re-check the "
                "token from @BotFather and make sure the bot still exists."
            ) from exc

        # Fetch identities (names/usernames) and channel titles so the dashboard
        # can show exactly who is connected and to which source channel.
        await self._load_identities()

        # Resolve every source channel once and filter on the entities
        # themselves. A raw "https://t.me/..." string is not guaranteed to match
        # inside the event filter, which silently produced no events — so a
        # channel that fails to resolve falls back to its raw configured value.
        self._source_entities = []
        self._source_titles = []
        for raw in self.source_channels:
            entity = None
            try:
                entity = await self.user_client.get_entity(raw)
            except Exception:  # noqa: BLE001 - fall back to the configured value
                logger.warning(
                    "Could not resolve source channel %r; using it as-is",
                    raw,
                    exc_info=True,
                )
            self._source_entities.append(entity if entity is not None else raw)
            title = self._entity_title(entity) if entity is not None else None
            self._source_titles.append(title or (raw if isinstance(raw, str) else _entity_id(raw)))

        # Keep the first resolved entity for backwards-compatible fields.
        self._source_entity = self._source_entities[0] if self._source_entities else None

        self._handler = self.user_client.add_event_handler(
            self._on_new_message,
            events.NewMessage(chats=self._source_entities),
        )

        self._running = True
        self._start_time = datetime.now(timezone.utc)
        logger.info(
            "TelegramReposter started. Listening on %d channel(s): %s; posting to %s",
            len(self._source_entities),
            ", ".join(
                f"{t} (id={_entity_id(e)})"
                for t, e in zip(self._source_titles, self._source_entities)
            ),
            self.destination_channel,
        )
        await self._emit(
            "status",
            {
                "running": True,
                "mode": self.repost_mode,
                "started_at": self._start_time.isoformat(),
                "user": dict(self._user_info),
                "bot": dict(self._bot_info),
                "source_title": self._source_title,
                "source_titles": list(self._source_titles),
            },
        )

    async def stop(self) -> None:
        """Disconnect both clients and mark as stopped."""
        if not self._running:
            logger.info("TelegramReposter not running; nothing to stop")
            return
        self._running = False
        logger.info("Stopping TelegramReposter")

        if self.user_client is not None:
            if self._handler is not None:
                try:
                    self.user_client.remove_event_handler(self._handler)
                except Exception:  # noqa: BLE001
                    logger.debug("Failed to remove event handler", exc_info=True)
            try:
                await self.user_client.disconnect()
            except Exception:  # noqa: BLE001
                logger.warning("Error disconnecting user client", exc_info=True)

        if self.bot_client is not None:
            try:
                await self.bot_client.disconnect()
            except Exception:  # noqa: BLE001
                logger.warning("Error disconnecting bot client", exc_info=True)

        self.user_client = None
        self.bot_client = None
        self._handler = None
        # NOTE: identity caches (self._user_info / self._bot_info) are kept so the
        # dashboard can still display the last-known names while stopped.
        await self._emit(
            "status",
            {
                "running": False,
                "mode": self.repost_mode,
                "user": self._client_view(None, self._user_info),
                "bot": self._client_view(None, self._bot_info),
                "source_title": self._source_title,
            },
        )

    @property
    def running(self) -> bool:
        return self._running

    # ------------------------------------------------------------------
    # Identity helpers
    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Client factory / identity helpers
    # ------------------------------------------------------------------
    def _session_path(self, name: str) -> str:
        """Absolute base path for a session file (no ``.session`` suffix)."""
        if self.base_dir:
            return str(Path(self.base_dir) / name)
        return name

    async def _start_bot_client(self) -> TelegramClient:
        """Return an authorised bot client matching the configured token.

        Reuses the cached session only when it belongs to the same bot id as the
        token; otherwise drops it and signs in fresh so a newly configured bot
        replaces the old identity instead of being ignored.
        """
        base = self._session_path(f"{self.session_name}_bot")
        expected_id = bot_id_from_token(self.bot_token)

        client = TelegramClient(base, self.api_id, self.api_hash)
        await client.connect()

        me = None
        if await client.is_user_authorized():
            try:
                me = await client.get_me()
            except Exception:  # noqa: BLE001 - treat as stale
                me = None

        if me is not None and (expected_id is None or getattr(me, "id", None) == expected_id):
            return client

        logger.info(
            "Bot session does not match the configured token (session id=%s, token id=%s); re-authenticating",
            getattr(me, "id", None),
            expected_id,
        )
        try:
            await client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        remove_session_files(base)

        client = TelegramClient(base, self.api_id, self.api_hash)
        await client.start(bot_token=self.bot_token)
        if await client.get_me() is None:
            raise RuntimeError("bot sign-in did not return an identity")
        return client

    @staticmethod
    def _person_view(me: Any) -> Dict[str, Any]:
        """Turn a Telethon ``get_me()`` result into a JSON-friendly dict."""
        if me is None:
            return {}
        first = getattr(me, "first_name", "") or ""
        last = getattr(me, "last_name", "") or ""
        name = (first + " " + last).strip() or getattr(me, "username", "") or ""
        return {
            "id": getattr(me, "id", None),
            "name": name,
            "username": getattr(me, "username", None),
            "first_name": first or None,
            "last_name": last or None,
            "phone": getattr(me, "phone", None),
            "is_bot": bool(getattr(me, "bot", False)),
        }

    @staticmethod
    def _entity_title(entity: Any) -> Optional[str]:
        """Best-effort display title for a channel/user entity."""
        if entity is None:
            return None
        if isinstance(entity, str):
            return entity
        title = getattr(entity, "title", None)
        if title:
            return str(title)
        first = getattr(entity, "first_name", "") or ""
        last = getattr(entity, "last_name", "") or ""
        name = (first + " " + last).strip()
        if name:
            return name
        username = getattr(entity, "username", None)
        if username:
            return "@" + str(username)
        return None

    async def _load_identities(self) -> None:
        """Populate cached identity + channel-title info (never fatal)."""
        # User account identity
        try:
            if self.user_client is not None:
                me = await self.user_client.get_me()
                self._user_info = self._person_view(me)
        except Exception:  # noqa: BLE001 - identity is a nice-to-have
            logger.warning("Could not fetch user identity", exc_info=True)

        # Bot identity
        try:
            if self.bot_client is not None:
                me = await self.bot_client.get_me()
                self._bot_info = self._person_view(me)
        except Exception:  # noqa: BLE001
            logger.warning("Could not fetch bot identity", exc_info=True)

        # Source channel title (resolved with the user client, which can see it)
        try:
            if self.user_client is not None and self.source_channel:
                entity = await self.user_client.get_entity(self.source_channel)
                self._source_title = self._entity_title(entity)
        except Exception:  # noqa: BLE001
            logger.warning("Could not resolve source channel title", exc_info=True)

        # Destination channel title
        try:
            if self.bot_client is not None and self.destination_channel:
                entity = await self.bot_client.get_entity(self.destination_channel)
                self._dest_title = self._entity_title(entity)
        except Exception:  # noqa: BLE001
            logger.warning("Could not resolve destination channel title", exc_info=True)

    def _client_view(self, client: Optional[TelegramClient], info: Dict[str, Any]) -> Dict[str, Any]:
        """Describe one client's connection state for the dashboard."""
        connected = bool(client is not None and client.is_connected())
        view: Dict[str, Any] = {
            "connected": connected,
            "name": info.get("name"),
            "username": info.get("username"),
            "id": info.get("id"),
            "is_bot": info.get("is_bot", False),
        }
        return view

    def status(self) -> Dict[str, Any]:
        source_ids = [_entity_id(c) for c in self.source_channels]
        return {
            "running": self._running,
            "mode": self.repost_mode,
            "source_channel": _entity_id(self.source_channel),
            "source_channels": source_ids,
            "source_titles": list(self._source_titles) or list(self.source_channels),
            "destination_channel": _entity_id(self.destination_channel),
            "source_title": self._source_title,
            "destination_title": self._dest_title,
            "user": self._client_view(self.user_client, self._user_info),
            "bot": self._client_view(self.bot_client, self._bot_info),
            "started_at": self._start_time.isoformat() if self._start_time else None,
            "uptime_seconds": (
                (datetime.now(timezone.utc) - self._start_time).total_seconds()
                if self._start_time and self._running
                else 0.0
            ),
        }

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------
    async def _on_new_message(self, event: events.NewMessage.Event) -> None:
        """Handle a new message on the source channel."""
        message: Message = event.message
        if message is None:
            return
        # Ignore service messages (joins, pins, etc.).
        if getattr(message, "action", None) is not None and not getattr(message, "message", None):
            return
        # Messages posted *by the signed-in account* in the source channel are
        # regular content and must be reposted too (``message.out`` is True for
        # them). Echo protection is handled by watching the source only, plus
        # the explicit source==destination guard below.
        chat_id = _entity_id(getattr(message, "chat_id", None))
        logger.info(
            "New source message id=%s chat=%s out=%s text=%r",
            getattr(message, "id", None),
            chat_id,
            getattr(message, "out", False),
            (getattr(message, "message", "") or "")[:40],
        )

        received_at = time.perf_counter()
        await self._process_message(message, received_at)

    def _source_id_for(self, message: Message) -> str:
        """Return the configured source channel a message actually came from.

        Messages arrive from any of the watched channels; match the message's
        ``chat_id`` against the resolved entities so the feed and the history
        attribute each repost to the right source. Falls back to the first
        source when nothing matches.
        """
        chat_id = getattr(message, "chat_id", None)
        if chat_id is not None:
            for raw, entity in zip(self.source_channels, self._source_entities):
                entity_id = getattr(entity, "id", None)
                if entity_id is not None:
                    # message.chat_id is the marked id (-100...); compare the
                    # raw entity id against both the raw and marked forms.
                    if entity_id == chat_id:
                        return _entity_id(raw)
        return _entity_id(self.source_channel)

    async def _process_message(self, message: Message, received_at: float) -> None:
        source_id = self._source_id_for(message)
        dest_id = _entity_id(self.destination_channel)
        content_type = _content_type(message)
        preview = _text_preview(message)

        dest_msg_id: Optional[int] = None
        status = "success"
        error: Optional[BaseException] = None

        try:
            dest_msg_id = await self._send_with_retry(message)
        except Exception as exc:  # noqa: BLE001 - recorded and reported below
            status = "error"
            error = exc
            logger.error("Failed to repost message %s: %s", message.id, exc)

        latency_ms = (time.perf_counter() - received_at) * 1000.0

        try:
            row_id = await database.log_message(
                source_msg_id=message.id,
                destination_msg_id=dest_msg_id,
                source_channel=source_id,
                dest_channel=dest_id,
                content_type=content_type,
                text_preview=preview,
                forwarded_at=datetime.now(timezone.utc),
                latency_ms=latency_ms,
                status=status,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Could not persist message record for %s", message.id)
            row_id = None

        if error is not None:
            try:
                await database.log_error(
                    error_type=type(error).__name__,
                    error_msg=str(error),
                    context=f"source_msg_id={message.id} mode={self.repost_mode}",
                )
            except Exception:  # noqa: BLE001
                logger.exception("Could not persist error record")

        payload = {
            "id": row_id,
            "source_msg_id": message.id,
            "destination_msg_id": dest_msg_id,
            "source_channel": source_id,
            "dest_channel": dest_id,
            "content_type": content_type,
            "text_preview": preview,
            "latency_ms": round(latency_ms, 2),
            "status": status,
            "mode": self.repost_mode,
        }
        await self._emit("message", payload)

    # ------------------------------------------------------------------
    # Sending with retry
    # ------------------------------------------------------------------
    async def _send_with_retry(self, message: Message) -> int:
        """Send the message using the configured mode, retrying on failure."""
        max_attempts = int(self.retry_settings.get("max_attempts", 3))
        backoff = float(self.retry_settings.get("backoff_seconds", 2))

        last_exc: Optional[BaseException] = None
        for attempt in range(1, max_attempts + 1):
            try:
                return await self._send(message)
            except FloodWaitError as exc:
                # Respect Telegram's mandated wait; do not count it as a failure.
                logger.warning("FloodWait: sleeping %s seconds", exc.seconds)
                await asyncio.sleep(exc.seconds)
                last_exc = exc
            except (SlowModeWaitError, MessageNotModifiedError) as exc:
                logger.warning("Telegram asked to slow down: %s", exc)
                await asyncio.sleep(backoff * attempt)
                last_exc = exc
            except RPCError as exc:
                last_exc = exc
                logger.warning("RPC error on attempt %d/%d: %s", attempt, max_attempts, exc)
                if attempt < max_attempts:
                    await asyncio.sleep(backoff * attempt)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning("Unexpected error on attempt %d/%d: %s", attempt, max_attempts, exc)
                if attempt < max_attempts:
                    await asyncio.sleep(backoff * attempt)

        assert last_exc is not None
        raise last_exc

    async def _send(self, message: Message) -> int:
        """Copy the message to the destination and return the destination msg id."""
        if self.bot_client is None:
            raise RuntimeError("Bot client is not connected")

        # Optional configurable delay before posting.
        delay_cfg = self.delay_settings or {}
        if delay_cfg.get("enabled"):
            lo = float(delay_cfg.get("min_seconds", 0))
            hi = float(delay_cfg.get("max_seconds", 0))
            if hi > lo:
                wait = lo + (hi - lo) * (asyncio.get_event_loop().time() % 1.0)
            else:
                wait = lo
            if wait > 0:
                await asyncio.sleep(wait)

        sent = await self.copy_message(message)
        return sent.id

    async def copy_message(self, message: Message) -> Message:
        """Copy the message (text/media) to the destination channel.

        Text is sent directly by the bot. Media is downloaded through the user
        client (which can see the source channel) and re-uploaded by the bot:
        the bot is not a member of the source, so it cannot fetch the file by
        itself, and a ``Message`` object cannot be reused across clients.
        """
        if self.bot_client is None:
            raise RuntimeError("Bot client is not connected")

        caption = message.message or ""

        if message.media is None:
            sent = await self.bot_client.send_message(
                self.destination_channel, message=caption
            )
            if isinstance(sent, list):
                return sent[0]
            return sent

        return await self._copy_media(message, caption)

    async def _copy_media(self, message: Message, caption: str) -> Message:
        """Download the media with the user client, upload it with the bot."""
        if self.bot_client is None:
            raise RuntimeError("Bot client is not connected")

        ext = _media_extension(message)
        tmp_path = Path(tempfile.gettempdir()) / f"repost_{message.chat_id}_{message.id}{ext}"
        try:
            downloaded = await message.download_media(file=str(tmp_path))
            if not downloaded:
                logger.warning(
                    "Media for message %s could not be downloaded; falling back to text",
                    message.id,
                )
                sent = await self.bot_client.send_message(
                    self.destination_channel, message=caption
                )
                return sent[0] if isinstance(sent, list) else sent

            sent = await self.bot_client.send_file(
                self.destination_channel,
                file=downloaded,
                caption=caption,
            )
            return sent[0] if isinstance(sent, list) else sent
        finally:
            try:
                if tmp_path.exists():
                    tmp_path.unlink()
            except OSError:  # noqa: BLE001 - temp cleanup is best-effort
                logger.debug("Could not delete temp media %s", tmp_path)

    # ------------------------------------------------------------------
    # Interactive authentication helper
    # ------------------------------------------------------------------
    async def authenticate(self, phone: str, code_callback: Callable[[], str]) -> None:
        """Perform the one-time interactive login for the user session.

        ``code_callback`` is a zero-argument callable that returns the login
        code the user received. This is intentionally not used automatically
        so credentials are never hard-coded.
        """
        if self.user_client is None:
            self.user_client = TelegramClient(self.session_name, self.api_id, self.api_hash)
            await self.user_client.connect()
        await self.user_client.sign_in(phone=phone, code_callback=code_callback)


# ----------------------------------------------------------------------
# Lightweight identity probe (works while the reposter is stopped)
# ----------------------------------------------------------------------
PROBE_TIMEOUT = 20.0


async def probe_identities(
    api_id: Optional[int],
    api_hash: Optional[str],
    bot_token: Optional[str],
    session_name: str = "reposter_session",
    source_channel: Any = None,
    destination_channel: Any = None,
    base_dir: Optional[str] = None,
    source_channels: Optional[List[Any]] = None,
) -> Dict[str, Any]:
    """Connect briefly to report both identities, even when stopped.

    The dashboard must be able to show the signed-in user, the configured bot
    and the channel titles at all times, not only while the reposter is running. This opens
    short-lived clients, reads the identities, resolves the channel titles and
    disconnects immediately so the session files are released for the reposter.

    Every section fails softly: a broken bot token or an unreadable source
    channel never prevents the rest of the snapshot from being returned.
    """
    def _base(name: str) -> str:
        return str(Path(base_dir) / name) if base_dir else name

    # Fold the legacy single source and the new list into one watched set.
    watched_sources = TelegramReposter._normalise_source_channels(
        source_channels, source_channel
    )

    result: Dict[str, Any] = {
        "user": {"connected": False, "name": None, "username": None, "id": None},
        "bot": {"connected": False, "name": None, "username": None, "id": None},
        "source_title": None,
        "source_titles": [],
        "destination_title": None,
        "user_error": None,
        "bot_error": None,
    }

    if not api_id or not api_hash:
        result["user_error"] = "api_id/api_hash are not configured"
        result["bot_error"] = "api_id/api_hash are not configured"
        return result

    user_client: Optional[TelegramClient] = None
    bot_client: Optional[TelegramClient] = None

    try:
        # ---- user account -------------------------------------------------
        try:
            user_client = TelegramClient(_base(session_name), int(api_id), str(api_hash))
            await asyncio.wait_for(user_client.connect(), PROBE_TIMEOUT)
            if await user_client.is_user_authorized():
                me = await asyncio.wait_for(user_client.get_me(), PROBE_TIMEOUT)
                info = TelegramReposter._person_view(me)
                result["user"] = {
                    "connected": True,
                    "authorized": True,
                    "name": info.get("name"),
                    "username": info.get("username"),
                    "id": info.get("id"),
                }
                for raw in watched_sources:
                    try:
                        entity = await asyncio.wait_for(
                            user_client.get_entity(raw), PROBE_TIMEOUT
                        )
                        title = TelegramReposter._entity_title(entity)
                    except Exception:  # noqa: BLE001 - title is optional
                        title = None
                        logger.debug("probe: source title unavailable", exc_info=True)
                    result["source_titles"].append(
                        title or (raw if isinstance(raw, str) else _entity_id(raw))
                    )
                if result["source_titles"]:
                    result["source_title"] = result["source_titles"][0]
            else:
                result["user_error"] = "user session is not authorized"
        except Exception as exc:  # noqa: BLE001
            result["user_error"] = str(exc)
            logger.debug("probe: user identity failed", exc_info=True)

        # ---- bot account --------------------------------------------------
        if bot_token:
            try:
                expected_id = bot_id_from_token(bot_token)
                bot_base = _base(f"{session_name}_bot")
                bot_client = TelegramClient(bot_base, int(api_id), str(api_hash))
                await asyncio.wait_for(bot_client.connect(), PROBE_TIMEOUT)

                me = None
                if await bot_client.is_user_authorized():
                    try:
                        me = await asyncio.wait_for(bot_client.get_me(), PROBE_TIMEOUT)
                    except Exception:  # noqa: BLE001
                        me = None

                if me is None or (expected_id is not None and getattr(me, "id", None) != expected_id):
                    try:
                        await bot_client.disconnect()
                    except Exception:  # noqa: BLE001
                        pass
                    remove_session_files(bot_base)
                    bot_client = TelegramClient(bot_base, int(api_id), str(api_hash))
                    await asyncio.wait_for(
                        bot_client.start(bot_token=bot_token), PROBE_TIMEOUT
                    )
                    me = await asyncio.wait_for(bot_client.get_me(), PROBE_TIMEOUT)

                info = TelegramReposter._person_view(me)
                result["bot"] = {
                    "connected": True,
                    "authorized": True,
                    "name": info.get("name"),
                    "username": info.get("username"),
                    "id": info.get("id"),
                }
                if destination_channel:
                    try:
                        entity = await asyncio.wait_for(
                            bot_client.get_entity(destination_channel), PROBE_TIMEOUT
                        )
                        result["destination_title"] = TelegramReposter._entity_title(entity)
                    except Exception:  # noqa: BLE001 - title is optional
                        logger.debug("probe: destination title unavailable", exc_info=True)
            except Exception as exc:  # noqa: BLE001
                result["bot_error"] = str(exc)
                logger.debug("probe: bot identity failed", exc_info=True)
        else:
            result["bot_error"] = "bot_token is not configured"

        # Fall back to the raw configured channels when a title is missing.
        if not result["source_titles"] and watched_sources:
            result["source_titles"] = [
                s if isinstance(s, str) else _entity_id(s) for s in watched_sources
            ]
        if result["source_titles"] and not result["source_title"]:
            result["source_title"] = result["source_titles"][0]
        if not result["destination_title"] and destination_channel:
            result["destination_title"] = _entity_id(destination_channel) if not isinstance(destination_channel, str) else destination_channel
    finally:
        for client in (user_client, bot_client):
            if client is not None:
                try:
                    await client.disconnect()
                except Exception:  # noqa: BLE001
                    pass

    return result
