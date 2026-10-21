"""Analytics engine for the Telegram reposter.

Thin async layer over :mod:`database` that computes the numbers the dashboard
needs: real-time snapshot, success rate, messages per hour, latency percentiles
and a JSON export. Everything is a coroutine so it can be called directly from
FastAPI request handlers and the WebSocket broadcaster.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import database

logger = logging.getLogger(__name__)


async def get_summary(days: int = 7) -> Dict[str, Any]:
    """Return the headline numbers for the dashboard header.

    Computed directly from the raw ``messages`` table (not the daily roll-up)
    so the numbers are correct immediately, even before the rollup task runs.
    """
    conn = await database._conn()
    cursor = await conn.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN status != 'success' THEN 1 ELSE 0 END) AS errors
        FROM messages
        WHERE julianday(forwarded_at) >= julianday('now', ?)
        """,
        (f"-{int(days)} days",),
    )
    row = await cursor.fetchone()
    total_day = int(row["total"] or 0)
    total_errors = int(row["errors"] or 0)
    success_rate = (
        round((total_day - total_errors) / total_day * 100.0, 2) if total_day > 0 else 100.0
    )

    total = await database.get_message_count()
    latency = await database.get_latency_stats(days=days)

    return {
        "total_messages": total,
        "messages_last_days": total_day,
        "errors_last_days": total_errors,
        "success_rate": success_rate,
        "avg_latency_ms": latency["avg_ms"],
        "p95_latency_ms": latency["p95_ms"],
        "min_latency_ms": latency["min_ms"],
        "max_latency_ms": latency["max_ms"],
    }


async def get_realtime_stats() -> Dict[str, Any]:
    """Return a point-in-time snapshot suitable for live dashboard updates."""
    now = datetime.now(timezone.utc)
    last_24h = now - timedelta(hours=24)
    last_hour = now - timedelta(hours=1)

    total = await database.get_message_count()
    last_24h_count = await database.get_message_count(since=last_24h)
    last_hour_count = await database.get_message_count(since=last_hour)
    latency = await database.get_latency_stats(days=1)
    per_hour = await database.get_messages_per_hour(hours=24)
    recent = await database.get_recent_messages(limit=20)

    return {
        "generated_at": now.isoformat(),
        "total_messages": total,
        "messages_last_hour": last_hour_count,
        "messages_last_24h": last_24h_count,
        "avg_latency_ms": latency["avg_ms"],
        "p95_latency_ms": latency["p95_ms"],
        "min_latency_ms": latency["min_ms"],
        "max_latency_ms": latency["max_ms"],
        "messages_per_hour": per_hour,
        "recent_messages": recent,
    }


async def get_success_rate(days: int = 7) -> Dict[str, Any]:
    """Return success/error counts and the success rate over ``days``."""
    conn = await database._conn()
    cursor = await conn.execute(
        """
        SELECT status, COUNT(*) AS n
        FROM messages
        WHERE julianday(forwarded_at) >= julianday('now', ?)
        GROUP BY status
        """,
        (f"-{int(days)} days",),
    )
    counts = {row["status"]: int(row["n"]) for row in await cursor.fetchall()}
    success = counts.get("success", 0)
    failed = sum(n for status, n in counts.items() if status != "success")
    total = success + failed
    return {
        "success": success,
        "failed": failed,
        "total": total,
        "success_rate": round(success / total * 100.0, 2) if total > 0 else 100.0,
        "days": days,
    }


async def get_messages_per_hour(hours: int = 24) -> List[Dict[str, Any]]:
    """Return message counts bucketed per hour."""
    return await database.get_messages_per_hour(hours=hours)


async def get_latency_stats(days: int = 7) -> Dict[str, Any]:
    """Return latency statistics (avg/min/max/p95) over the raw messages table."""
    return await database.get_latency_stats(days=days)


async def get_latency_series(days: int = 7) -> List[Dict[str, Any]]:
    """Return per-day latency aggregates for charting."""
    daily = await database.get_daily_stats(days=days)
    return [
        {
            "date": d["date"],
            "avg_ms": d["avg_latency"],
            "min_ms": d["min_latency"],
            "max_ms": d["max_latency"],
            "total": d["total_messages"],
        }
        for d in daily
    ]


async def export_stats(days: int = 7) -> Dict[str, Any]:
    """Export a complete statistics snapshot as JSON."""
    return await database.export_stats_json(days=days)


async def refresh_daily_stats(target_date: Optional[date] = None) -> Dict[str, Any]:
    """Recompute the daily aggregate row (called after each message)."""
    return await database.upsert_daily_stats(target_date=target_date)


async def run_periodic_rollup(interval_seconds: int = 300) -> None:
    """Background task that periodically recomputes daily aggregates.

    Runs forever until cancelled; intended to be spawned as an asyncio task.
    """
    logger.info("Daily stats rollup task started (interval=%ss)", interval_seconds)
    while True:
        try:
            await refresh_daily_stats()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Daily stats rollup failed")
        await asyncio.sleep(interval_seconds)
