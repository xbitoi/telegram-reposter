"""FastAPI application for the Telegram channel reposter.

Exposes the REST API used by the dashboard, a WebSocket endpoint for live
updates, and (when present) the static frontend from ``../frontend/``.

Run with::

    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import analytics
import auth
import config as config_module
import database
import errors as error_catalog
from login_manager import login_session
from telegram_client import TelegramReposter
from telegram_client import probe_identities as telegram_probe

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

# ----------------------------------------------------------------------
# Pydantic models
# ----------------------------------------------------------------------
class DelaySettings(BaseModel):
    enabled: bool = False
    min_seconds: float = 0.0
    max_seconds: float = 0.0


class RetrySettings(BaseModel):
    max_attempts: int = 3
    backoff_seconds: float = 2.0


class ConfigUpdate(BaseModel):
    api_id: Optional[int] = None
    api_hash: Optional[str] = None
    bot_token: Optional[str] = None
    session_name: Optional[str] = None
    source_channel: Optional[Any] = None
    source_channels: Optional[List[Any]] = None
    destination_channel: Optional[Any] = None
    repost_mode: Optional[str] = None
    delay_settings: Optional[DelaySettings] = None
    retry: Optional[RetrySettings] = None


# ----------------------------------------------------------------------
# WebSocket manager
# ----------------------------------------------------------------------
class ConnectionManager:
    """Tracks connected dashboard clients and broadcasts events to them."""

    def __init__(self) -> None:
        self._connections: List[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.append(websocket)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)
        logger.info("WebSocket client disconnected (%d total)", len(self._connections))

    async def broadcast(self, event_name: str, payload: Dict[str, Any]) -> None:
        message = {"event": event_name, "data": payload}
        disconnected: List[WebSocket] = []
        async with self._lock:
            targets = list(self._connections)
        for ws in targets:
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - dead socket, drop it
                disconnected.append(ws)
        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    if ws in self._connections:
                        self._connections.remove(ws)


manager = ConnectionManager()

# ----------------------------------------------------------------------
# Global state
# ----------------------------------------------------------------------
reposter: Optional[TelegramReposter] = None
_rollup_task: Optional[asyncio.Task] = None
_stats_task: Optional[asyncio.Task] = None


async def _on_repost_event(event_name: str, payload: Dict[str, Any]) -> None:
    """Bridge reposter events into the WebSocket broadcast bus."""
    await manager.broadcast(event_name, payload)


def _build_reposter(cfg: config_module.Config) -> TelegramReposter:
    """Construct a TelegramReposter from the current configuration."""
    return TelegramReposter(
        api_id=cfg.get("api_id"),
        api_hash=cfg.get("api_hash"),
        bot_token=cfg.get("bot_token"),
        session_name=cfg.get("session_name", "reposter_session"),
        source_channel=cfg.get("source_channel"),
        source_channels=cfg.get("source_channels"),
        destination_channel=cfg.get("destination_channel"),
        repost_mode=cfg.get("repost_mode", "copy"),
        delay_settings=cfg.get("delay_settings"),
        retry_settings=cfg.get("retry"),
        base_dir=str(Path(cfg.path).resolve().parent) if getattr(cfg, "path", None) else None,
    )


# ----------------------------------------------------------------------
# Identity snapshot (shown even when the reposter is stopped)
# ----------------------------------------------------------------------
_IDENTITY_TTL = 30.0  # seconds
_identity_cache: Dict[str, Any] = {"at": 0.0, "data": None}
_identity_lock = asyncio.Lock()
# Serialises anything that opens the Telegram session files (start/stop and the
# identity probe). Without it the probe locks the SQLite session while the
# reposter is connecting, producing "database is locked".
_session_guard = asyncio.Lock()


def _invalidate_identities() -> None:
    """Drop the cached identity snapshot so the next read re-probes Telegram."""
    _identity_cache["at"] = 0.0
    _identity_cache["data"] = None


async def _identity_snapshot(force: bool = False) -> Dict[str, Any]:
    """Return user/bot/channel identities, probing Telegram when needed.

    Results are cached briefly to keep the 15-second dashboard poll cheap; the
    cache is invalidated whenever the configuration changes so a new bot or
    channel is reflected immediately.
    """
    now = time.monotonic()
    cached = _identity_cache.get("data")
    if not force and cached is not None and (now - _identity_cache["at"]) < _IDENTITY_TTL:
        return cached

    async with _identity_lock:
        now = time.monotonic()
        cached = _identity_cache.get("data")
        if not force and cached is not None and (now - _identity_cache["at"]) < _IDENTITY_TTL:
            return cached

        cfg = config_module.config

        # Never touch the session files while the reposter runs or while the
        # interactive login flow holds the user session.
        if (reposter is not None and reposter.running) or login_session.step in (
            "code_sent",
            "password_needed",
        ):
            if cached is not None:
                return cached
            return {
                "user": {"connected": False, "name": None, "username": None, "id": None},
                "bot": {"connected": False, "name": None, "username": None, "id": None},
                "source_title": cfg.get("source_channel"),
                "source_titles": list(cfg.get("source_channels") or []),
                "destination_title": cfg.get("destination_channel"),
            }

        try:
            async with _session_guard:
                data = await asyncio.wait_for(
                    telegram_probe(
                        api_id=cfg.get("api_id"),
                        api_hash=cfg.get("api_hash"),
                        bot_token=cfg.get("bot_token"),
                        session_name=cfg.get("session_name", "reposter_session"),
                        source_channel=cfg.get("source_channel"),
                        source_channels=cfg.get("source_channels"),
                        destination_channel=cfg.get("destination_channel"),
                        base_dir=str(Path(cfg.path).resolve().parent)
                        if getattr(cfg, "path", None)
                        else None,
                    ),
                    timeout=25.0,
                )
        except Exception:  # noqa: BLE001 - never break the status endpoint
            logger.exception("Identity probe failed")
            data = {
                "user": {"connected": False, "name": None, "username": None, "id": None},
                "bot": {"connected": False, "name": None, "username": None, "id": None},
                "source_title": cfg.get("source_channel"),
                "source_titles": list(cfg.get("source_channels") or []),
                "destination_title": cfg.get("destination_channel"),
            }
        _identity_cache["data"] = data
        _identity_cache["at"] = time.monotonic()
        return data


async def _status_payload() -> Dict[str, Any]:
    """Full status payload: runtime state plus always-available identities."""
    cfg = config_module.config

    if reposter is not None and reposter.running:
        # While running the live clients are authoritative.
        return reposter.status()

    snap = await _identity_snapshot()
    return {
        "running": False,
        "mode": cfg.get("repost_mode"),
        "source_channel": cfg.get("source_channel"),
        "source_channels": list(cfg.get("source_channels") or []),
        "destination_channel": cfg.get("destination_channel"),
        "source_title": snap.get("source_title") or cfg.get("source_channel"),
        "source_titles": snap.get("source_titles")
        or list(cfg.get("source_channels") or []),
        "destination_title": snap.get("destination_title") or cfg.get("destination_channel"),
        "user": snap.get("user") or {"connected": False, "name": None, "username": None},
        "bot": snap.get("bot") or {"connected": False, "name": None, "username": None},
        "started_at": None,
        "uptime_seconds": 0.0,
        "user_error": snap.get("user_error"),
        "bot_error": snap.get("bot_error"),
    }


async def _periodic_stats_broadcast(interval_seconds: int = 10) -> None:
    """Broadcast a stats snapshot periodically so dashboards stay live."""
    while True:
        try:
            stats = await analytics.get_realtime_stats()
            await manager.broadcast("stats", stats)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Periodic stats broadcast failed")
        await asyncio.sleep(interval_seconds)


# ----------------------------------------------------------------------
# Lifespan
# ----------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = config_module.config
    cfg.load()
    await database.init_db()
    logger.info("Database initialised at %s", database.DB_PATH)

    # Populate the daily roll-up once at startup so the chart has data.
    try:
        await analytics.refresh_daily_stats()
    except Exception:  # noqa: BLE001
        logger.exception("Initial daily stats rollup failed")

    global _rollup_task, _stats_task
    _rollup_task = asyncio.create_task(analytics.run_periodic_rollup(300))
    _stats_task = asyncio.create_task(_periodic_stats_broadcast(10))

    yield

    global reposter
    if reposter is not None and reposter.running:
        await reposter.stop()
    for task in (_rollup_task, _stats_task):
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    await database.close_db()
    logger.info("Shutdown complete")


app = FastAPI(title="Telegram Reposter", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _detect_lang(request: Request) -> str:
    """Read ?lang= from the query string, defaulting to English."""
    lang = request.query_params.get("lang", "en")
    return "ar" if str(lang).lower().startswith("ar") else "en"


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic validation failures into the same structured error shape."""
    lang = _detect_lang(request)
    field = ""
    try:
        errs = exc.errors()
        if errs:
            loc = errs[0].get("loc") or []
            field = str(loc[-1]) if loc else ""
    except Exception:  # noqa: BLE001 - never fail while reporting a failure
        field = ""

    label = field.replace("_", " ") or "input"
    detail = f"invalid value for '{field or 'request body'}'"
    body = error_catalog.build_error("CONFIG_INVALID", lang=lang, detail=detail)
    if field:
        body["title"] = (
            f"قيمة غير صالحة للحقل: {field}" if lang == "ar"
            else f"Invalid value for field: {field}"
        )
    body["detail"] = detail
    return JSONResponse(status_code=422, content={"detail": body})


# Serve the frontend if it exists; otherwise the API still works standalone.
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIR)), name="static")
    logger.info("Serving frontend from %s", FRONTEND_DIR)
else:
    logger.warning("Frontend directory %s not found; serving API only", FRONTEND_DIR)


# ----------------------------------------------------------------------
# Dashboard authentication
# ----------------------------------------------------------------------
_PUBLIC_PATHS = {
    "/",
    "/favicon.ico",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
}


def _auth_refusal(code: str, status: int, lang: str = "en") -> JSONResponse:
    """Structured 401/429 payload the dashboard gate can render directly."""
    return JSONResponse(
        status_code=status,
        content={"detail": error_catalog.build_error(code, lang=lang)},
    )


def _set_auth_cookie(response: JSONResponse, token: str) -> JSONResponse:
    response.set_cookie(
        auth.COOKIE_NAME,
        token,
        max_age=auth.TOKEN_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        path="/",
    )
    return response


@app.middleware("http")
async def dashboard_guard(request: Request, call_next):
    """Refuse every API call until the operator has unlocked the dashboard."""
    path = request.url.path
    if (
        path in _PUBLIC_PATHS
        or path.startswith("/assets/")
        or path.startswith("/api/auth/")
        or not path.startswith("/api/")
    ):
        return await call_next(request)

    lang = _detect_lang(request)
    # No password stored, or the lock switched off: the dashboard is open.
    if not await auth.is_enabled():
        return await call_next(request)
    if not await auth.token_is_valid(request.cookies.get(auth.COOKIE_NAME)):
        return _auth_refusal("AUTH_REQUIRED", 401, lang)
    return await call_next(request)


class AuthPassword(BaseModel):
    password: str = ""


class AuthChange(BaseModel):
    current: str = ""
    new_password: str = ""
    confirm: str = ""


@app.get("/api/auth/state")
async def auth_state(request: Request):
    """Tell the dashboard whether a password exists and this browser is unlocked."""
    return await auth.state(request.cookies.get(auth.COOKIE_NAME))


@app.post("/api/auth/setup")
async def auth_setup(body: AuthPassword, lang: str = "en"):
    """Create the first dashboard password (only while none exists)."""
    if await auth.is_configured():
        return _auth_refusal("AUTH_REQUIRED", 409, lang)
    if not auth.password_length_ok(body.password):
        raise HTTPException(
            status_code=400,
            detail=error_catalog.build_error("AUTH_PASSWORD_SHORT", lang=lang),
        )
    await auth.set_password(body.password)
    response = JSONResponse({"status": "created", "authenticated": True})
    return _set_auth_cookie(response, await auth.issue_token())


@app.post("/api/auth/login")
async def auth_login(body: AuthPassword, lang: str = "en"):
    """Verify the dashboard password and issue an HttpOnly session cookie."""
    ok, reason = await auth.verify_password(body.password)
    if not ok:
        code = {
            "locked": "AUTH_LOCKED",
            "not_configured": "AUTH_SETUP_REQUIRED",
        }.get(reason, "AUTH_INVALID_PASSWORD")
        status = {"locked": 429, "not_configured": 401}.get(reason, 401)
        raise HTTPException(
            status_code=status, detail=error_catalog.build_error(code, lang=lang)
        )
    response = JSONResponse({"status": "ok", "authenticated": True})
    return _set_auth_cookie(response, await auth.issue_token())


@app.post("/api/auth/logout")
async def auth_logout():
    """Forget the session cookie."""
    response = JSONResponse({"status": "signed_out", "authenticated": False})
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return response


@app.post("/api/auth/disable")
async def auth_disable(request: Request, body: AuthPassword, lang: str = "en"):
    """Turn the lock screen off (requires the current password)."""
    if not await auth.is_enabled():
        return {"status": "already_disabled", "enabled": False}
    ok, reason = await auth.verify_password(body.password)
    if not ok:
        code = {
            "locked": "AUTH_LOCKED",
            "not_configured": "AUTH_SETUP_REQUIRED",
        }.get(reason, "AUTH_INVALID_PASSWORD")
        status = {"locked": 429, "not_configured": 401}.get(reason, 401)
        raise HTTPException(
            status_code=status, detail=error_catalog.build_error(code, lang=lang)
        )
    await auth.disable()
    response = JSONResponse({"status": "disabled", "enabled": False})
    response.delete_cookie(auth.COOKIE_NAME, path="/")
    return response


@app.post("/api/auth/password")
async def auth_change_password(body: AuthChange, lang: str = "en"):
    """Change the dashboard password (current password required)."""
    if body.new_password != body.confirm:
        raise HTTPException(
            status_code=400,
            detail=error_catalog.build_error("AUTH_PASSWORD_MISMATCH", lang=lang),
        )
    ok, reason = await auth.change_password(body.current, body.new_password)
    if not ok:
        code = {
            "too_short": "AUTH_PASSWORD_SHORT",
            "locked": "AUTH_LOCKED",
            "not_configured": "AUTH_SETUP_REQUIRED",
        }.get(reason, "AUTH_INVALID_PASSWORD")
        status = {"too_short": 400, "locked": 429, "not_configured": 401}.get(reason, 401)
        raise HTTPException(
            status_code=status, detail=error_catalog.build_error(code, lang=lang)
        )
    response = JSONResponse({"status": "updated", "authenticated": True})
    return _set_auth_cookie(response, await auth.issue_token())


# ----------------------------------------------------------------------
# REST API
# ----------------------------------------------------------------------
@app.get("/")
async def index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return JSONResponse(
        {
            "service": "Telegram Reposter",
            "status": "running",
            "docs": "/docs",
            "frontend": str(FRONTEND_DIR) if FRONTEND_DIR.exists() else None,
        }
    )


@app.get("/api/config")
async def get_config():
    """Return the current configuration with secrets masked."""
    return config_module.config.as_dict()


@app.post("/api/config")
async def update_config(update: ConfigUpdate, lang: str = "en"):
    """Update configuration and persist it to backend/.env.

    On failure returns a structured, localised error object describing the
    problem, a hint and the steps to fix it (see :mod:`errors`).

    Saving always refreshes the identity snapshot so a newly entered bot token
    or channel is reflected in the dashboard immediately. If the reposter is
    running it is restarted with the new configuration, otherwise the old
    clients would keep using the previous bot/channel.
    """
    global reposter
    payload = {k: v for k, v in update.dict().items() if v is not None}
    # update.dict() already unwraps nested pydantic models into plain dicts.
    try:
        saved = config_module.config.update(payload)
    except config_module.ConfigError as exc:
        err = error_catalog.build_error(
            error_catalog.classify(str(exc)), lang=lang, detail=str(exc)
        )
        raise HTTPException(status_code=err.get("status", 400), detail=err) from exc

    # A changed configuration invalidates both the cached identities and the
    # live clients.
    _invalidate_identities()

    restart_error = None
    was_running = reposter is not None and reposter.running
    if was_running:
        async with _session_guard:
            try:
                await reposter.stop()
            except Exception:  # noqa: BLE001
                logger.exception("Failed to stop reposter during config reload")
            reposter = None
            try:
                reposter = _build_reposter(config_module.config)
                reposter.on_event(_on_repost_event)
                try:
                    await login_session.disconnect()
                except Exception:  # noqa: BLE001
                    pass
                await reposter.start()
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to restart reposter after config change")
                reposter = None
                restart_error = error_catalog.from_exception(exc, lang=lang)

    identities = await _identity_snapshot(force=True)
    if reposter is not None and reposter.running:
        status_payload = reposter.status()
    else:
        cfg = config_module.config
        status_payload = {
            "running": False,
            "mode": cfg.get("repost_mode"),
            "source_channel": cfg.get("source_channel"),
            "source_channels": list(cfg.get("source_channels") or []),
            "destination_channel": cfg.get("destination_channel"),
            "source_title": identities.get("source_title") or cfg.get("source_channel"),
            "source_titles": identities.get("source_titles")
            or list(cfg.get("source_channels") or []),
            "destination_title": identities.get("destination_title")
            or cfg.get("destination_channel"),
            "user": identities.get("user"),
            "bot": identities.get("bot"),
            "started_at": None,
            "uptime_seconds": 0.0,
            "user_error": identities.get("user_error"),
            "bot_error": identities.get("bot_error"),
        }

    return {
        "config": saved,
        "status": status_payload,
        "restarted": bool(was_running and reposter is not None and reposter.running),
        "restart_error": restart_error,
    }


@app.get("/api/stats")
async def get_stats(days: int = 7):
    """Return headline statistics."""
    return await analytics.get_summary(days=days)


@app.get("/api/stats/latency")
async def get_latency(days: int = 7):
    """Return latency statistics (avg/min/max/p95)."""
    return await analytics.get_latency_stats(days=days)


@app.get("/api/stats/hourly")
async def get_hourly(hours: int = 24):
    """Return messages-per-hour buckets."""
    return {"buckets": await analytics.get_messages_per_hour(hours=hours)}


@app.get("/api/messages")
async def get_messages(limit: int = 50, offset: int = 0):
    """Return recent reposted messages."""
    return {"messages": await database.get_recent_messages(limit=limit, offset=offset)}


@app.post("/api/stats/reset")
async def reset_stats():
    """Zero every counter while keeping the message history visible."""
    info = await database.reset_counters()
    await analytics.refresh_daily_stats()
    return {
        "status": "reset",
        "counters_since": info.get("counters_since"),
        "stats": await analytics.get_realtime_stats(),
        "summary": await analytics.get_summary(days=7),
        "hourly": await analytics.get_messages_per_hour(hours=24),
    }


@app.post("/api/messages/clear")
async def clear_messages():
    """Delete the message log and the error log, and reset the counters."""
    info = await database.clear_history()
    await analytics.refresh_daily_stats()
    return {
        "status": "cleared",
        "deleted": info,
        "stats": await analytics.get_realtime_stats(),
        "summary": await analytics.get_summary(days=7),
        "hourly": await analytics.get_messages_per_hour(hours=24),
        "messages": await database.get_recent_messages(limit=50),
        "errors": await database.get_recent_errors(limit=50),
    }


@app.get("/api/errors")
async def get_errors(limit: int = 50, lang: str = "en"):
    """Return recent error entries, each enriched with a structured explainer."""
    rows = await database.get_recent_errors(limit=limit)
    enriched: List[Dict[str, Any]] = []
    for row in rows:
        raw = f"{row.get('error_type', '')}: {row.get('error_msg', '')}"
        info = error_catalog.from_exception(Exception(raw), lang=lang)
        merged = dict(row)
        merged["code"] = info["code"]
        merged["title"] = info["title"]
        merged["explain"] = info["message"]
        merged["hint"] = info["hint"]
        merged["steps"] = info["steps"]
        enriched.append(merged)
    return {"errors": enriched}


@app.post("/api/start")
async def start_reposter(lang: str = "en"):
    """Start the reposter using the current configuration.

    On failure returns a structured, localised error object (code, title,
    message, hint, steps) so the dashboard can guide the user precisely.
    """
    global reposter
    cfg = config_module.config
    if reposter is not None and reposter.running:
        return {
            "status": "already_running",
            "error": error_catalog.build_error("ALREADY_RUNNING", lang=lang),
            "detail": reposter.status(),
        }

    reposter = _build_reposter(cfg)
    reposter.on_event(_on_repost_event)
    try:
        async with _session_guard:
            # The interactive login keeps a client on the same .session file while
            # the user is signing in. Release it before the reposter opens the file,
            # otherwise SQLite reports "database is locked" and start fails.
            try:
                await login_session.disconnect()
            except Exception:  # noqa: BLE001 - releasing is best-effort
                logger.warning("Could not release the login session before start", exc_info=True)
            await reposter.start()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to start reposter")
        reposter = None
        _invalidate_identities()
        err = error_catalog.from_exception(exc, lang=lang)
        raise HTTPException(status_code=err.get("status", 400), detail=err) from exc
    _invalidate_identities()
    return {"status": "started", "detail": reposter.status()}


@app.post("/api/stop")
async def stop_reposter():
    """Stop the reposter."""
    global reposter
    if reposter is None or not reposter.running:
        return {"status": "not_running", "detail": await _status_payload()}
    async with _session_guard:
        await reposter.stop()
        reposter = None
    _invalidate_identities()
    return {"status": "stopped", "detail": await _status_payload()}


@app.get("/api/status")
async def get_status():
    """Return runtime state plus the user/bot/channel identities.

    Identities are reported even when the reposter is stopped so the dashboard
    always shows who is signed in and which bot is configured.
    """
    return await _status_payload()


@app.get("/api/export")
async def export_stats(days: int = 7):
    """Export a full statistics snapshot as JSON."""
    return await analytics.export_stats(days=days)


# ----------------------------------------------------------------------
# User-account login (drives the dashboard sign-in panel)
# ----------------------------------------------------------------------
class LoginStart(BaseModel):
    phone: str = ""


class LoginCode(BaseModel):
    code: str = ""


class LoginPassword(BaseModel):
    password: str = ""


@app.get("/api/login/status")
async def login_status(lang: str = "en"):
    """Return the current login step so the panel survives a page reload.

    While the reposter holds the session file this endpoint must not re-open it
    (SQLite would report "database is locked"), so the live identity of the
    running client is reported instead.
    """
    if reposter is not None and reposter.running:
        live = reposter.status()
        return {
            "step": "authorized",
            "phone": None,
            "user": live.get("user"),
            "authorized": bool((live.get("user") or {}).get("authorized")),
            "session_path": None,
            "error": None,
        }
    return await login_session.refresh(lang=lang)


@app.post("/api/login/start")
async def login_start(body: LoginStart, lang: str = "en"):
    """Send the Telegram login code to the given phone number."""
    result = await login_session.start(body.phone, lang=lang)
    if not result.get("ok"):
        err = result.get("error") or {}
        raise HTTPException(status_code=err.get("status", 400), detail=err)
    return result


@app.post("/api/login/code")
async def login_code(body: LoginCode, lang: str = "en"):
    """Submit the login code; may return password_needed for 2FA accounts."""
    result = await login_session.submit_code(body.code, lang=lang)
    if not result.get("ok"):
        err = result.get("error") or {}
        raise HTTPException(status_code=err.get("status", 400), detail=err)
    if (result.get("status") or {}).get("authorized"):
        _invalidate_identities()
    return result


@app.post("/api/login/password")
async def login_password(body: LoginPassword, lang: str = "en"):
    """Finish two-step verification login."""
    result = await login_session.submit_password(body.password, lang=lang)
    if not result.get("ok"):
        err = result.get("error") or {}
        raise HTTPException(status_code=err.get("status", 400), detail=err)
    if (result.get("status") or {}).get("authorized"):
        _invalidate_identities()
    return result


@app.post("/api/login/logout")
async def login_logout():
    """Sign out the user account and delete the stored session."""
    result = await login_session.logout()
    _invalidate_identities()
    return result


# ----------------------------------------------------------------------
# WebSocket
# ----------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Push live message events and periodic stats to the dashboard."""
    # Same lock as the REST API: no unlock cookie, no live stream.
    if await auth.is_enabled() and not await auth.token_is_valid(
        websocket.cookies.get(auth.COOKIE_NAME)
    ):
        await websocket.close(code=4401)
        return

    await manager.connect(websocket)
    try:
        # Send an immediate snapshot so a fresh client renders instantly.
        await websocket.send_json(
            {"event": "stats", "data": await analytics.get_realtime_stats()}
        )
        await websocket.send_json(
            {
                "event": "status",
                "data": reposter.status() if reposter else {
                    "running": False,
                    "mode": config_module.config.get("repost_mode"),
                    "user": {"connected": False},
                    "bot": {"connected": False},
                },
            }
        )
        while True:
            # Keep the socket alive; client may send ping/ignore messages.
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_json({"event": "pong", "data": {}})
    except WebSocketDisconnect:
        await manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        logger.debug("WebSocket loop ended", exc_info=True)
        await manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
