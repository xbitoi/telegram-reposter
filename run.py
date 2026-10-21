"""Main entry point for the Telegram auto-reposter.

Usage::

    python run.py

This script:

1. Loads the configuration from ``backend/.env`` (the single source of truth).
2. Starts the FastAPI application (uvicorn) on localhost:8000.

The database is initialised by the FastAPI lifespan handler in
``backend/main.py`` (``database.init_db()``), and the Telethon client is
started/stopped through the REST API endpoints ``POST /api/start`` and
``POST /api/stop``.
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

# ---------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"

# ``backend/main.py`` uses flat imports (``import config``, ``import database``,
# ``import analytics``, ``import telegram_client``), so the backend directory
# must be importable.
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import config as config_module  # noqa: E402

# Configuration lives in backend/.env; the singleton already points there.
config_module.config.load()

import main  # noqa: E402  (import after the config is loaded)


def run() -> None:
    """Start the uvicorn server (configuration is already loaded)."""
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )


if __name__ == "__main__":
    run()
