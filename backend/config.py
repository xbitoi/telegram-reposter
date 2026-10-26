"""Configuration management for the Telegram reposter backend.

Single source of truth: ``backend/.env``. Every credential (API id/hash, bot
token) and every channel lives there, and every script reads it through this
module, so there is no mixing between a YAML file and process environment.

On first run an existing ``config.yaml`` is migrated into ``.env`` and renamed
to ``config.yaml.legacy`` so it can never shadow the new file.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Any, Dict, Tuple

try:  # pragma: no cover - YAML is only needed for the one-time migration
    import yaml
except Exception:  # noqa: BLE001
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent
ENV_PATH = BACKEND_DIR / ".env"
LEGACY_YAML_PATH = BACKEND_DIR / "config.yaml"

# Default configuration used when .env has no value yet.
DEFAULT_CONFIG: Dict[str, Any] = {
    "api_id": 0,
    "api_hash": "",
    "bot_token": "",
    "session_name": "reposter_session",
    "source_channel": "",
    "source_channels": [],
    "destination_channel": "",
    "repost_mode": "copy",  # always "copy" (forward is not supported)
    # Basic build: a fixed 10-second pause before every repost.
    "delay_settings": {
        "enabled": True,
        "min_seconds": 10,
        "max_seconds": 10,
    },
    "retry": {
        "max_attempts": 3,
        "backoff_seconds": 2,
    },
}

# Top-level config key -> (env name, cast)
_ENV_MAP: Dict[str, Tuple[str, Any]] = {
    "api_id": ("TELEGRAM_API_ID", int),
    "api_hash": ("TELEGRAM_API_HASH", str),
    "bot_token": ("TELEGRAM_BOT_TOKEN", str),
    "session_name": ("TELEGRAM_SESSION_NAME", str),
    "source_channel": ("TELEGRAM_SOURCE_CHANNEL", str),
    "destination_channel": ("TELEGRAM_DESTINATION_CHANNEL", str),
    "repost_mode": ("REPOST_MODE", str),
}

# Nested config path -> (env name, kind)
_NESTED_ENV_MAP = {
    ("delay_settings", "enabled"): ("DELAY_ENABLED", "bool"),
    ("delay_settings", "min_seconds"): ("DELAY_MIN_SECONDS", "int"),
    ("delay_settings", "max_seconds"): ("DELAY_MAX_SECONDS", "int"),
    ("retry", "max_attempts"): ("RETRY_MAX_ATTEMPTS", "int"),
    ("retry", "backoff_seconds"): ("RETRY_BACKOFF_SECONDS", "int"),
}

ALL_ENV_NAMES = [name for name, _ in _ENV_MAP.values()] + [
    name for name, _ in _NESTED_ENV_MAP.values()
] + ["TELEGRAM_SOURCE_CHANNELS"]

# Separator used to store the source-channel list in a single env value.
_CHANNEL_SEP = ","


def _split_channels(raw: Any) -> list:
    """Parse a comma/newline separated channel list into a clean list of str."""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        text = str(raw).replace("\n", _CHANNEL_SEP)
        items = text.split(_CHANNEL_SEP)
    result = []
    seen = set()
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _join_channels(channels: Any) -> str:
    """Serialise a channel list into a single comma-separated string."""
    if isinstance(channels, str):
        return channels
    return _CHANNEL_SEP.join(_split_channels(channels))


def _cast_bool(raw: str) -> bool:
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _parse_env_file(path: Path) -> Dict[str, str]:
    """Parse a dotenv file into a plain dict (comments and quotes handled)."""
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return values
    for line in text.splitlines():
        line = line.strip().lstrip("\ufeff")
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _format_env_value(value: Any) -> str:
    """Serialise a value for the dotenv file (quote when it contains spaces)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = "" if value is None else str(value)
    if text == "" or any(ch in text for ch in " #\"'\t"):
        return '"' + text.replace('"', '\\"') + '"'
    return text


class ConfigError(RuntimeError):
    """Raised when the configuration is invalid or cannot be persisted."""


class Config:
    """Thread-safe dotenv-backed configuration store.

    Usage::

        config = Config()
        config.load()
        api_id = config.get("api_id")
        config.update({"api_id": 12345})
    """

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else ENV_PATH
        self._data: Dict[str, Any] = {}
        self._lock = threading.RLock()
        self._initialized = False

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    def load(self) -> Dict[str, Any]:
        """Read ``.env`` into memory (and into ``os.environ`` for other tools).

        Migration: when ``.env`` is missing but the legacy ``config.yaml``
        exists, its values are written into ``.env`` and the YAML file is
        renamed to ``config.yaml.legacy``. The dotenv file is authoritative;
        process environment variables only fill keys it does not define.
        """
        with self._lock:
            if not self.path.exists() and LEGACY_YAML_PATH.exists():
                self._migrate_from_yaml()

            file_values = _parse_env_file(self.path)

            data: Dict[str, Any] = dict(DEFAULT_CONFIG)
            for key, (env_name, cast) in _ENV_MAP.items():
                raw = file_values.get(env_name)
                if raw is None:
                    raw = os.getenv(env_name)
                if raw is not None and str(raw).strip() != "":
                    try:
                        data[key] = cast(raw)
                    except (TypeError, ValueError) as exc:
                        raise ConfigError(
                            f"{env_name} in .env is not valid: {exc}"
                        ) from exc

            for (section, key), (env_name, kind) in _NESTED_ENV_MAP.items():
                raw = file_values.get(env_name)
                if raw is None:
                    raw = os.getenv(env_name)
                if raw is None or str(raw).strip() == "":
                    continue
                section_data = dict(data.get(section) or {})
                try:
                    if kind == "bool":
                        section_data[key] = _cast_bool(str(raw))
                    else:
                        section_data[key] = int(str(raw))
                except (TypeError, ValueError) as exc:
                    raise ConfigError(
                        f"{env_name} in .env is not valid: {exc}"
                    ) from exc
                data[section] = section_data

            # Source-channel list: prefer the dedicated TELEGRAM_SOURCE_CHANNELS
            # value; fall back to the legacy single TELEGRAM_SOURCE_CHANNEL so an
            # existing .env keeps working unchanged.
            channels_raw = file_values.get("TELEGRAM_SOURCE_CHANNELS")
            if channels_raw is None:
                channels_raw = os.getenv("TELEGRAM_SOURCE_CHANNELS")
            parsed_channels = _split_channels(channels_raw)
            if not parsed_channels:
                parsed_channels = _split_channels(data.get("source_channel"))
            data["source_channels"] = parsed_channels
            # Keep the legacy key pointing at the first channel (backwards compat).
            if parsed_channels:
                data["source_channel"] = parsed_channels[0]

            # Expose the effective values to any helper that reads os.environ.
            for key, (env_name, _cast) in _ENV_MAP.items():
                os.environ[env_name] = str(data.get(key, ""))
            for (section, key), (env_name, _kind) in _NESTED_ENV_MAP.items():
                os.environ[env_name] = str((data.get(section) or {}).get(key, ""))
            os.environ["TELEGRAM_SOURCE_CHANNELS"] = _join_channels(data["source_channels"])

            self._data = data
            self._initialized = True
            return data

    def _migrate_from_yaml(self) -> None:
        """One-time migration of a legacy config.yaml into .env."""
        if yaml is None:
            return
        try:
            parsed = yaml.safe_load(LEGACY_YAML_PATH.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - a broken legacy file is not fatal
            logger.warning("Legacy config.yaml could not be read; skipping migration")
            return
        if not isinstance(parsed, dict):
            return

        merged = self._deep_merge(DEFAULT_CONFIG, parsed)
        try:
            self.path.write_text(self._render_env(merged), encoding="utf-8")
        except OSError as exc:
            raise ConfigError(f"Could not write {self.path}: {exc}") from exc

        legacy_target = LEGACY_YAML_PATH.with_suffix(".yaml.legacy")
        try:
            LEGACY_YAML_PATH.replace(legacy_target)
            logger.info(
                "Migrated config.yaml -> .env (legacy kept at %s)", legacy_target.name
            )
        except OSError:
            logger.warning("Migrated config.yaml -> .env but could not rename the old file")

    def save(self, data: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """Write the current configuration back to ``.env``.

        Unknown keys already present in the file are preserved, so hand-written
        extras are not lost. Returns the in-memory configuration.
        """
        with self._lock:
            if data is not None:
                self._data = self._deep_merge(DEFAULT_CONFIG, data)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(self._render_env(self._data), encoding="utf-8")
            except OSError as exc:
                raise ConfigError(f"Could not write {self.path}: {exc}") from exc

            # Keep the process environment in sync with what was just saved.
            for key, (env_name, _cast) in _ENV_MAP.items():
                os.environ[env_name] = str(self._data.get(key, ""))
            for (section, key), (env_name, _kind) in _NESTED_ENV_MAP.items():
                os.environ[env_name] = str((self._data.get(section) or {}).get(key, ""))
            return self._data

    def _render_env(self, data: Dict[str, Any]) -> str:
        """Render the dotenv file, preserving unrelated existing entries."""
        known = set(ALL_ENV_NAMES)
        preserved = {
            k: v for k, v in _parse_env_file(self.path).items() if k not in known
        }

        lines = [
            "# Telegram Reposter configuration",
            "# Single source of truth: this file. Edit here or from the dashboard.",
            "",
            "# --- Telegram API (https://my.telegram.org) ---",
            f"TELEGRAM_API_ID={_format_env_value(data.get('api_id', 0))}",
            f"TELEGRAM_API_HASH={_format_env_value(data.get('api_hash', ''))}",
            "",
            "# --- Bot (@BotFather) ---",
            f"TELEGRAM_BOT_TOKEN={_format_env_value(data.get('bot_token', ''))}",
            "",
            "# --- Channels ---",
            f"TELEGRAM_SOURCE_CHANNEL={_format_env_value(data.get('source_channel', ''))}",
            f"TELEGRAM_SOURCE_CHANNELS={_format_env_value(_join_channels(data.get('source_channels') or []))}",
            f"TELEGRAM_DESTINATION_CHANNEL={_format_env_value(data.get('destination_channel', ''))}",
            "",
            "# --- Behaviour ---",
            f"TELEGRAM_SESSION_NAME={_format_env_value(data.get('session_name', 'reposter_session'))}",
            f"REPOST_MODE={_format_env_value(data.get('repost_mode', 'copy'))}",
        ]

        delay = data.get("delay_settings") or {}
        lines += [
            f"DELAY_ENABLED={_format_env_value(bool(delay.get('enabled', False)))}",
            f"DELAY_MIN_SECONDS={_format_env_value(delay.get('min_seconds', 0))}",
            f"DELAY_MAX_SECONDS={_format_env_value(delay.get('max_seconds', 0))}",
        ]

        retry = data.get("retry") or {}
        lines += [
            f"RETRY_MAX_ATTEMPTS={_format_env_value(retry.get('max_attempts', 3))}",
            f"RETRY_BACKOFF_SECONDS={_format_env_value(retry.get('backoff_seconds', 2))}",
        ]

        if preserved:
            lines += ["", "# --- Extra entries ---"]
            lines += [f"{k}={_format_env_value(v)}" for k, v in preserved.items()]

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------
    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            if not self._initialized:
                self.load()
            return self._data.get(key, default)

    def as_dict(self) -> Dict[str, Any]:
        """Return a copy of the configuration, redacting secrets."""
        with self._lock:
            if not self._initialized:
                self.load()
            redacted = dict(self._data)
            if redacted.get("api_hash"):
                redacted["api_hash"] = self._mask(redacted["api_hash"])
            if redacted.get("bot_token"):
                redacted["bot_token"] = self._mask(redacted["bot_token"])
            return redacted

    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Merge updates into the current config and persist to ``.env``.

        Secret fields (``api_hash``, ``bot_token``) are protected against
        round-trip masking: if the incoming value is empty or still looks
        masked (contains ``*``), the previously stored value is kept so a
        masked value from the dashboard never overwrites the real secret.
        """
        with self._lock:
            if not self._initialized:
                self.load()
            clean: Dict[str, Any] = dict(updates)
            for secret in ("api_hash", "bot_token"):
                if secret in clean:
                    value = clean.get(secret)
                    if value is None:
                        clean.pop(secret, None)
                        continue
                    text = str(value)
                    if not text.strip() or "*" in text:
                        # Masked or blank: keep whatever is already stored.
                        clean.pop(secret, None)
            merged = self._deep_merge(self._data, clean)
            # Reconcile the single/list source fields so either input form works:
            # a list wins when provided, otherwise the legacy single value seeds
            # the list, and the legacy key always mirrors the first channel.
            merged = self._reconcile_source_channels(merged, clean)
            self._validate(merged)
            return self.save(merged)

    @staticmethod
    def _reconcile_source_channels(
        merged: Dict[str, Any], incoming: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Keep ``source_channels`` (list) and ``source_channel`` (single) in sync."""
        if "source_channels" in incoming:
            channels = _split_channels(incoming.get("source_channels"))
        elif "source_channel" in incoming:
            channels = _split_channels(incoming.get("source_channel"))
        else:
            channels = _split_channels(merged.get("source_channels"))
            if not channels:
                channels = _split_channels(merged.get("source_channel"))
        merged["source_channels"] = channels
        if channels:
            merged["source_channel"] = channels[0]
        return merged

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    def _validate(self, data: Dict[str, Any]) -> None:
        if not isinstance(data.get("api_id"), int) or data.get("api_id") <= 0:
            raise ConfigError("api_id must be a positive integer")
        api_hash = data.get("api_hash") or ""
        if not api_hash:
            raise ConfigError("api_hash must not be empty")
        if not data.get("bot_token"):
            raise ConfigError("bot_token must not be empty")
        if not _split_channels(data.get("source_channels")) and not _split_channels(
            data.get("source_channel")
        ):
            raise ConfigError("at least one source channel is required")
        # Copy is the only supported mode; anything else (including a legacy
        # "forward" value) is coerced so it can never block a save or reach the
        # reposter, which would then fail every message with ForwardMessagesRequest.
        if data.get("repost_mode") != "copy":
            data["repost_mode"] = "copy"
        delay = data.get("delay_settings") or {}
        if delay.get("enabled"):
            lo, hi = delay.get("min_seconds", 0), delay.get("max_seconds", 0)
            if lo < 0 or hi < lo:
                raise ConfigError("delay_settings min/max seconds are invalid")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge override into base without mutating either."""
        result = dict(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = Config._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _mask(value: str) -> str:
        if len(value) <= 8:
            return "*" * len(value)
        return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Config(path={self.path!r})"


# Module-level singleton used across the backend.
config = Config()
