"""SQLite analytics database for the Telegram reposter.

Uses aiosqlite for fully asynchronous access so no synchronous SQLite call ever
blocks the event loop. The database file lives next to this module
(analytics.db) and is created on first use with the three tables:

- messages:      one row per forwarded/copied message with latency and status.
- stats_daily:   per-day aggregates (totals and latency min/avg/max/errors).
- errors:        error log with type, message and context.

All public functions are coroutines.
"""

from __future__ import annotations

import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiosqlite

DB_PATH = Path(__file__).resolve().parent / "analytics.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    source_msg_id    INTEGER NOT NULL,
    destination_msg_id INTEGER,
    source_channel   TEXT NOT NULL,
    dest_channel     TEXT NOT NULL,
    content_type     TEXT NOT NULL,
    text_preview     TEXT,
    forwarded_at     TEXT NOT NULL,
    latency_ms       REAL NOT NULL,
    status           TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_forwarded_at
    ON messages (forwarded_at);

CREATE TABLE IF NOT EXISTS stats_daily (
    date          TEXT PRIMARY KEY,
    total_messages INTEGER NOT NULL DEFAULT 0,
    avg_latency   REAL NOT NULL DEFAULT 0,
    min_latency   REAL NOT NULL DEFAULT 0,
    max_latency   REAL NOT NULL DEFAULT 0,
    errors        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS errors (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL,
    error_type  TEXT NOT NULL,
    error_msg   TEXT NOT NULL,
    context     TEXT
);

CREATE TABLE IF NOT EXISTS app_meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);
"""

_db: Optional[aiosqlite.Connection] = None
_init_lock = None

# Aggregates ignore everything before the last "reset counters" action, while
# the history table keeps every row. An empty/missing value means "no floor".
_COUNTER_FLOOR_SQL = (
    "COALESCE((SELECT value FROM app_meta WHERE key = 'counters_since'), '')"
)


async def init_db(db_path: Path | str | None = None) -> aiosqlite.Connection:
    """Initialise the database, creating tables if needed.

    Safe to call multiple times; the first call wins.
    """
    global _db
    path = Path(db_path) if db_path else DB_PATH
    if _db is not None:
        return _db

    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    try:
        await conn.executescript(SCHEMA)
        await conn.commit()
    except Exception:
        await conn.close()
        raise
    _db = conn
    return _db


async def close_db() -> None:
    """Close the shared connection (used on shutdown)."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _conn() -> aiosqlite.Connection:
    """Return the shared connection, initialising it lazily."""
    if _db is None:
        return await init_db()
    return _db


# ----------------------------------------------------------------------
# Message logging
# ----------------------------------------------------------------------
async def log_message(
    source_msg_id: int,
    destination_msg_id: Optional[int],
    source_channel: str,
    dest_channel: str,
    content_type: str,
    text_preview: Optional[str],
    forwarded_at: Optional[datetime] = None,
    latency_ms: float = 0.0,
    status: str = "success",
) -> int:
    """Insert a message record and return its row id."""
    conn = await _conn()
    ts = (forwarded_at or datetime.now(timezone.utc)).isoformat()
    cursor = await conn.execute(
        """
        INSERT INTO messages
            (source_msg_id, destination_msg_id, source_channel, dest_channel,
             content_type, text_preview, forwarded_at, latency_ms, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_msg_id,
            destination_msg_id,
            source_channel,
            dest_channel,
            content_type,
            text_preview,
            ts,
            float(latency_ms),
            status,
        ),
    )
    await conn.commit()
    return cursor.lastrowid


async def get_recent_messages(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """Return the most recent messages, newest first."""
    conn = await _conn()
    cursor = await conn.execute(
        """
        SELECT id, source_msg_id, destination_msg_id, source_channel,
               dest_channel, content_type, text_preview, forwarded_at,
               latency_ms, status
        FROM messages
        ORDER BY forwarded_at DESC, id DESC
        LIMIT ? OFFSET ?
        """,
        (limit, offset),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_message_count(since: Optional[datetime] = None) -> int:
    """Count messages, optionally only those forwarded after ``since``."""
    conn = await _conn()
    if since is None:
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE forwarded_at >= {_COUNTER_FLOOR_SQL}"
        )
    else:
        cursor = await conn.execute(
            f"SELECT COUNT(*) FROM messages WHERE forwarded_at >= ? "
            f"AND forwarded_at >= {_COUNTER_FLOOR_SQL}",
            (since.isoformat(),),
        )
    row = await cursor.fetchone()
    return int(row[0]) if row else 0


# ----------------------------------------------------------------------
# Daily stats
# ----------------------------------------------------------------------
async def get_daily_stats(
    days: int = 7, target_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """Return daily aggregate rows.

    If ``target_date`` is given a single row is returned for that date,
    otherwise the last ``days`` rows ordered by date ascending are returned.
    Rows with no data are synthesised so dashboards get a continuous series.
    """
    conn = await _conn()
    if target_date is not None:
        cursor = await conn.execute(
            "SELECT date, total_messages, avg_latency, min_latency, max_latency, errors "
            "FROM stats_daily WHERE date = ?",
            (target_date.isoformat(),),
        )
        row = await cursor.fetchone()
        if row:
            return [dict(row)]
        return [
            {
                "date": target_date.isoformat(),
                "total_messages": 0,
                "avg_latency": 0.0,
                "min_latency": 0.0,
                "max_latency": 0.0,
                "errors": 0,
            }
        ]

    cursor = await conn.execute(
        "SELECT date, total_messages, avg_latency, min_latency, max_latency, errors "
        "FROM stats_daily ORDER BY date DESC LIMIT ?",
        (days,),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    rows.reverse()
    return rows


async def get_latency_stats(
    days: int = 7, target_date: Optional[date] = None
) -> Dict[str, Any]:
    """Return latency statistics (avg/min/max/p95) over the raw messages table.

    Uses the ``messages`` table rather than ``stats_daily`` so the numbers stay
    accurate even before the daily roll-up job has run.
    """
    conn = await _conn()
    since = None
    if target_date is not None:
        since = datetime.combine(
            target_date, datetime.min.time(), tzinfo=timezone.utc
        ).isoformat()
        until = datetime.combine(
            date.fromordinal(target_date.toordinal() + 1),
            datetime.min.time(),
            tzinfo=timezone.utc,
        ).isoformat()
        cursor = await conn.execute(
            f"""
            SELECT COUNT(*) AS n,
                   AVG(latency_ms) AS avg_ms,
                   MIN(latency_ms) AS min_ms,
                   MAX(latency_ms) AS max_ms
            FROM messages
            WHERE status = 'success' AND forwarded_at >= ? AND forwarded_at < ?
              AND forwarded_at >= {_COUNTER_FLOOR_SQL}
            """,
            (since, until),
        )
    else:
        cursor = await conn.execute(
            f"""
            SELECT COUNT(*) AS n,
                   AVG(latency_ms) AS avg_ms,
                   MIN(latency_ms) AS min_ms,
                   MAX(latency_ms) AS max_ms
            FROM messages
            WHERE status = 'success'
              AND julianday(forwarded_at) >= julianday('now', ?)
              AND forwarded_at >= {_COUNTER_FLOOR_SQL}
            """,
            (f"-{int(days)} days",),
        )
    row = await cursor.fetchone()
    n = int(row["n"]) if row else 0
    avg_ms = float(row["avg_ms"]) if row and row["avg_ms"] is not None else 0.0
    min_ms = float(row["min_ms"]) if row and row["min_ms"] is not None else 0.0
    max_ms = float(row["max_ms"]) if row and row["max_ms"] is not None else 0.0

    # p95 via a sorted fetch (datasets are small enough for this to be cheap).
    p95_ms = 0.0
    if target_date is not None:
        cursor = await conn.execute(
            f"SELECT latency_ms FROM messages WHERE status = 'success' "
            f"AND forwarded_at >= ? AND forwarded_at < ? "
            f"AND forwarded_at >= {_COUNTER_FLOOR_SQL} ORDER BY latency_ms",
            (since, until),
        )
    else:
        cursor = await conn.execute(
            f"SELECT latency_ms FROM messages WHERE status = 'success' "
            f"AND julianday(forwarded_at) >= julianday('now', ?) "
            f"AND forwarded_at >= {_COUNTER_FLOOR_SQL} ORDER BY latency_ms",
            (f"-{int(days)} days",),
        )
    latencies = [float(r[0]) for r in await cursor.fetchall()]
    if latencies:
        idx = min(len(latencies) - 1, int(round(0.95 * (len(latencies) - 1))))
        p95_ms = latencies[idx]

    return {
        "count": n,
        "avg_ms": round(avg_ms, 2),
        "min_ms": round(min_ms, 2),
        "max_ms": round(max_ms, 2),
        "p95_ms": round(p95_ms, 2),
        "days": days,
    }


async def get_messages_per_hour(
    hours: int = 24, target_date: Optional[date] = None
) -> List[Dict[str, Any]]:
    """Return message counts bucketed per hour for the last ``hours`` hours."""
    conn = await _conn()
    cursor = await conn.execute(
        f"""
        SELECT strftime('%Y-%m-%dT%H:00:00', forwarded_at) AS bucket,
               COUNT(*) AS total
        FROM messages
        WHERE julianday(forwarded_at) >= julianday('now', ?)
          AND forwarded_at >= {_COUNTER_FLOOR_SQL}
        GROUP BY bucket
        ORDER BY bucket ASC
        """,
        (f"-{int(hours)} hours",),
    )
    rows = [dict(r) for r in await cursor.fetchall()]
    # Fill missing buckets with zeros so the chart has a continuous axis.
    filled: List[Dict[str, Any]] = []
    if rows:
        from datetime import timedelta

        start = datetime.fromisoformat(rows[0]["bucket"])
        end = datetime.fromisoformat(rows[-1]["bucket"])
        by_hour = {r["bucket"]: int(r["total"]) for r in rows}
        current = start
        while current <= end:
            key = current.strftime("%Y-%m-%dT%H:00:00")
            filled.append({"bucket": key, "total": by_hour.get(key, 0)})
            current += timedelta(hours=1)
    return filled


async def upsert_daily_stats(
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """Recompute and store the aggregate row for ``target_date`` (default today)."""
    conn = await _conn()
    day = target_date or datetime.now(timezone.utc).date()
    start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc).isoformat()
    end = datetime.combine(
        date.fromordinal(day.toordinal() + 1),
        datetime.min.time(),
        tzinfo=timezone.utc,
    ).isoformat()

    cursor = await conn.execute(
        f"""
        SELECT COUNT(*) AS total,
               AVG(CASE WHEN status = 'success' THEN latency_ms END) AS avg_ms,
               MIN(CASE WHEN status = 'success' THEN latency_ms END) AS min_ms,
               MAX(CASE WHEN status = 'success' THEN latency_ms END) AS max_ms,
               SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS errors
        FROM messages
        WHERE forwarded_at >= ? AND forwarded_at < ?
          AND forwarded_at >= {_COUNTER_FLOOR_SQL}
        """,
        (start, end),
    )
    row = await cursor.fetchone()
    total = int(row["total"] or 0)
    avg_ms = float(row["avg_ms"] or 0.0)
    min_ms = float(row["min_ms"] or 0.0)
    max_ms = float(row["max_ms"] or 0.0)
    errors = int(row["errors"] or 0)

    await conn.execute(
        """
        INSERT INTO stats_daily (date, total_messages, avg_latency, min_latency, max_latency, errors)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            total_messages = excluded.total_messages,
            avg_latency    = excluded.avg_latency,
            min_latency    = excluded.min_latency,
            max_latency    = excluded.max_latency,
            errors         = excluded.errors
        """,
        (day.isoformat(), total, avg_ms, min_ms, max_ms, errors),
    )
    await conn.commit()
    return {
        "date": day.isoformat(),
        "total_messages": total,
        "avg_latency": round(avg_ms, 2),
        "min_latency": round(min_ms, 2),
        "max_latency": round(max_ms, 2),
        "errors": errors,
    }


async def log_error(
    error_type: str,
    error_msg: str,
    context: Optional[str] = None,
    timestamp: Optional[datetime] = None,
) -> int:
    """Persist an error entry and return its row id."""
    conn = await _conn()
    ts = (timestamp or datetime.now(timezone.utc)).isoformat()
    cursor = await conn.execute(
        "INSERT INTO errors (timestamp, error_type, error_msg, context) VALUES (?, ?, ?, ?)",
        (ts, error_type, error_msg, context),
    )
    await conn.commit()
    return cursor.lastrowid


async def get_recent_errors(limit: int = 50) -> List[Dict[str, Any]]:
    """Return the most recent error entries, newest first."""
    conn = await _conn()
    cursor = await conn.execute(
        "SELECT id, timestamp, error_type, error_msg, context "
        "FROM errors ORDER BY timestamp DESC, id DESC LIMIT ?",
        (limit,),
    )
    return [dict(r) for r in await cursor.fetchall()]


async def export_stats_json(days: int = 7) -> Dict[str, Any]:
    """Export a full statistics snapshot as a JSON-serialisable dict."""
    daily = await get_daily_stats(days=days)
    latency = await get_latency_stats(days=days)
    per_hour = await get_messages_per_hour(hours=24)
    recent_errors = await get_recent_errors(limit=50)
    total = await get_message_count()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_messages": total,
        "daily": daily,
        "latency": latency,
        "messages_per_hour": per_hour,
        "recent_errors": recent_errors,
    }


# ----------------------------------------------------------------------
# Maintenance: counters reset / history clear
# ----------------------------------------------------------------------
async def get_meta(key: str) -> Optional[str]:
    """Read a value from the ``app_meta`` key/value table."""
    conn = await _conn()
    cursor = await conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,))
    row = await cursor.fetchone()
    return row["value"] if row else None


async def set_meta(key: str, value: str) -> None:
    """Write a value into the ``app_meta`` key/value table."""
    conn = await _conn()
    await conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    await conn.commit()


async def reset_counters() -> Dict[str, Any]:
    """Zero every aggregate without deleting the message history.

    A ``counters_since`` watermark is stored so all aggregate queries ignore
    rows that came before this moment, while the feed keeps its full history.
    """
    conn = await _conn()
    stamp = datetime.now(timezone.utc).isoformat()
    await conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('counters_since', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (stamp,),
    )
    await conn.execute("DELETE FROM stats_daily")
    await conn.commit()
    return {"counters_since": stamp}


async def clear_history() -> Dict[str, int]:
    """Delete the message log and the error log, and reset the counters."""
    conn = await _conn()
    cursor = await conn.execute("DELETE FROM messages")
    messages_deleted = cursor.rowcount or 0
    cursor = await conn.execute("DELETE FROM errors")
    errors_deleted = cursor.rowcount or 0
    await conn.execute("DELETE FROM stats_daily")
    await conn.execute(
        "INSERT INTO app_meta (key, value) VALUES ('counters_since', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (datetime.now(timezone.utc).isoformat(),),
    )
    await conn.commit()
    return {"messages_deleted": messages_deleted, "errors_deleted": errors_deleted}
