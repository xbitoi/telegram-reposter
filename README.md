# Telegram Reposter Dashboard

A self-hosted, bilingual (English / العربية) dashboard that mirrors posts from
one or more Telegram source channels into a destination channel, with live
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

- Python 3.11+
- A Telegram API id/hash from <https://my.telegram.org>
- A bot token from [@BotFather](https://t.me/BotFather), added as an admin in
  the destination channel
- A Telegram user session signed in once (phone + code) so the user client can
  read the source channels

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
| `DELAY_*`, `RETRY_*` | Optional posting delay and retry policy |

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
