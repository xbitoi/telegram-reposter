"""One-time interactive login for the Telegram *user* account (Telethon).

Why this exists
---------------
A Telegram bot can only read a channel it administers. To read an arbitrary
source channel the reposter uses a real *user* account over MTProto. That
account must sign in once (phone number + login code, plus the 2FA password if
enabled) so Telethon can persist a session file. After that the reposter starts
with no prompt, forever.

Usage
-----
    cd backend
    python login.py

It reads api_id / api_hash / session_name from the same .env the app uses, so there is nothing to type twice except the phone number (you can also
pass it: ``python login.py +2126XXXXXXXX``).

The session file is written next to this script (``reposter_session.session``),
exactly where telegram_client.py expects it.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
)

import config as config_module

HERE = Path(__file__).resolve().parent


def _mask(value: str, keep: int = 4) -> str:
    if not value:
        return "(empty)"
    if len(value) <= keep * 2:
        return value[0] + "*" * (len(value) - 1)
    return value[:keep] + "*" * (len(value) - keep * 2) + value[-keep:]


async def login() -> int:
    cfg = config_module.config
    api_id = cfg.get("api_id")
    api_hash = cfg.get("api_hash")
    session_name = cfg.get("session_name") or "reposter_session"

    if not api_id or not api_hash:
        print("[X] api_id / api_hash are missing in backend/.env. Fill them first.")
        return 2

    # Put the session file exactly where telegram_client.py builds it.
    session_path = str(HERE / session_name)

    print("=" * 60)
    print("  Telegram user-account login (one time)")
    print("=" * 60)
    print(f"  api_id      : {api_id}")
    print(f"  api_hash    : {_mask(str(api_hash))}")
    print(f"  session file: {session_path}.session")
    print("-" * 60)

    client = TelegramClient(session_path, int(api_id), str(api_hash))

    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print(f"[OK] Already signed in as {me.first_name or ''} "
              f"(@{me.username}) id={me.id}")
        await client.disconnect()
        return 0

    # --- Phone number -------------------------------------------------
    phone = sys.argv[1] if len(sys.argv) > 1 else None
    if not phone:
        phone = input("Phone number (international format, e.g. +2126...): ").strip()
    if not phone:
        print("[X] No phone number given. Aborted.")
        await client.disconnect()
        return 2

    try:
        sent = await client.send_code_request(phone)
    except PhoneNumberInvalidError:
        print("[X] That phone number is not valid. Use the international format "
              "with the country code, e.g. +2126XXXXXXXX.")
        await client.disconnect()
        return 3
    except Exception as exc:  # noqa: BLE001 - surface anything the API says
        print(f"[X] Could not request a login code: {exc}")
        await client.disconnect()
        return 3

    print(f"[i] A login code was sent to you inside Telegram (not SMS). "
          f"Code hash: {sent.phone_code_hash[:8]}...")

    # --- Login code ---------------------------------------------------
    code = input("Login code: ").strip()
    if not code:
        print("[X] No code given. Aborted.")
        await client.disconnect()
        return 3

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        # --- Two-step verification (2FA) password ---------------------
        print("[i] Two-step verification is enabled on this account.")
        password = input("2FA password: ").strip()
        if not password:
            print("[X] No password given. Aborted.")
            await client.disconnect()
            return 3
        try:
            await client.sign_in(password=password)
        except Exception as exc:  # noqa: BLE001
            print(f"[X] 2FA failed: {exc}")
            await client.disconnect()
            return 4
    except PhoneCodeInvalidError:
        print("[X] The login code is wrong. Run the script again.")
        await client.disconnect()
        return 3
    except PhoneCodeExpiredError:
        print("[X] The login code expired. Run the script again.")
        await client.disconnect()
        return 3
    except Exception as exc:  # noqa: BLE001
        print(f"[X] Sign-in failed: {exc}")
        await client.disconnect()
        return 3

    me = await client.get_me()
    print("-" * 60)
    print(f"[OK] Signed in successfully as {me.first_name or ''} "
          f"{me.last_name or ''} (@{me.username}) id={me.id}.")
    print(f"[OK] Session saved to {session_path}.session")
    print("[OK] You can now start the reposter from the dashboard — no more prompts.")
    await client.disconnect()
    return 0


def main() -> None:
    try:
        code = asyncio.run(login())
    except KeyboardInterrupt:
        print("\n[X] Cancelled by user.")
        sys.exit(130)
    sys.exit(code)


if __name__ == "__main__":
    main()
