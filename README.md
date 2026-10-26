# Telegram Reposter Dashboard

A self-hosted, bilingual (English / العربية) dashboard that mirrors posts from
a Telegram source channel into a destination channel, with live
analytics, latency charts, error tracking and an optional dashboard password
gate.

The reposting core is a **user client** (Telethon) that listens on the source
channels plus a **bot client** that publishes to the destination. Media is
downloaded by the user account and re-uploaded by the bot, so the bot never
needs to be a member of the source channel.

## Features

- **Copy mode only** — messages are mirrored as native copies (text, photo,
  video, document, audio, sticker, …). Forwarding is intentionally not
  supported because a bot cannot forward from a channel it does not belong to.
- **Live dashboard** — WebSocket feed of every repost with latency, content
  type and status.
- **Analytics** — summary counters, daily stats, per-hour buckets and latency
  (avg / min / max / p95) charts (Chart.js).
- **Error log** — every failure is stored with its type, message and context.
- **Bilingual UI** — full English / Arabic interface with automatic RTL.
- **Dashboard password gate** — optional password protected with
  PBKDF2-HMAC-SHA256 (200k iterations), signed HttpOnly session cookie and a
  brute-force lockout.
- **Safe reset** — clear history or zero the counters from the UI with a
  confirmation modal.
- **One-click launchers** — `start.bat` / `install.bat` for Windows.

## Requirements

- **Windows 11** - this build is tested on Windows 11 only. Other operating
  systems are untested (it is plain Python 3.11+, so it may run elsewhere, but
  nobody has verified it).
- A Telegram API id/hash from <https://my.telegram.org>. The dashboard ships
  with a built-in step-by-step guide that walks you through creating them.
- A bot token from [@BotFather](https://t.me/BotFather). The bot must already
  be a member of the destination channel (added as an admin) before it can
  post there.
- A Telegram user account that **is already a member of the source channel**.
  The user client signs in once (phone + code) and listens there, so the bot
  never has to join the source.

## Basic build

This build is limited to **1 source channel and 1 destination channel**.

## Installation

```bat
install.bat
```

Or manually:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

All settings live in `backend/.env` (copy `backend/.env.example` to start):

| Key | Meaning |
| --- | --- |
| `TELEGRAM_API_ID` | API id from my.telegram.org |
| `TELEGRAM_API_HASH` | API hash from my.telegram.org |
| `TELEGRAM_BOT_TOKEN` | Bot token (admin of the destination) |
| `TELEGRAM_SOURCE_CHANNEL` | Source channel(s) to listen on |
| `TELEGRAM_DESTINATION_CHANNEL` | Destination channel |
| `REPOST_MODE` | Fixed to `copy` |
| `DELAY_ENABLED` | Delay between reposts (ships as `true`) |
| `DELAY_MIN_SECONDS` / `DELAY_MAX_SECONDS` | Delay window in seconds (ships as `10` / `10`) |
| `RETRY_*` | Retry policy for failed posts |

## Repost delay

This build ships with a **fixed 10-second delay** before every repost
(`DELAY_ENABLED=true`, `DELAY_MIN_SECONDS=10`, `DELAY_MAX_SECONDS=10`), so a
busy source channel is mirrored at a calm pace instead of a burst. The values
can be edited in `backend/.env` before starting the app.

## Running

```bat
start.bat
```

Then open <http://localhost:8000>.

## Project layout

```
backend/     FastAPI app, Telethon client, SQLite analytics, auth
frontend/    Vanilla HTML/CSS/JS dashboard (no build step)
data/        Runtime data (git-ignored)
start.bat    Launcher
install.bat  Dependency installer
```

## License

Provided as-is for personal use.
