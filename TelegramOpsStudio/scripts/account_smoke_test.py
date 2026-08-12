from __future__ import annotations

import argparse
import asyncio
import getpass
import tempfile
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


def parse_args():
    parser = argparse.ArgumentParser(description="Authorize a temporary Telegram session for connectivity testing.")
    parser.add_argument("--api-id", required=True, type=int)
    parser.add_argument("--phone", required=True)
    return parser.parse_args()


async def run(api_id: int, phone: str) -> None:
    api_hash = getpass.getpass("API Hash (hidden): ").strip()
    if not api_hash:
        raise SystemExit("API Hash is required")
    with tempfile.TemporaryDirectory(prefix="telegram-ops-smoke-") as tmp:
        session = str(Path(tmp) / "smoke")
        client = TelegramClient(session, api_id, api_hash)
        await client.connect()
        try:
            print(f"[1/4] Connected: {client.is_connected()}")
            if not await client.is_user_authorized():
                sent = await client.send_code_request(phone)
                print("[2/4] Login code requested")
                code = input("Login code: ").strip()
                try:
                    await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
                except SessionPasswordNeededError:
                    await client.sign_in(password=getpass.getpass("2FA password: "))
            print(f"[3/4] Authorized: {await client.is_user_authorized()}")
            me = await client.get_me()
            print(f"[4/4] Account ID: {me.id}; username: @{me.username or ''}")
            print("Smoke test PASS. Temporary session will now be deleted.")
        finally:
            await client.disconnect()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(run(args.api_id, args.phone))
