from __future__ import annotations

import argparse
import asyncio
import getpass
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError


def parse_args():
    p = argparse.ArgumentParser(description='Read-only Telegram account login smoke test')
    p.add_argument('--api-id', type=int, required=True)
    p.add_argument('--phone', required=True)
    p.add_argument('--session-name', default='smoke_test')
    return p.parse_args()


async def main():
    args = parse_args()
    api_hash = getpass.getpass('API Hash (hidden): ').strip()
    if len(api_hash) != 32:
        raise SystemExit('API Hash must be 32 hex characters.')

    session_dir = Path.home() / '.telegram_ops_studio' / 'test_sessions'
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = session_dir / args.session_name

    client = TelegramClient(str(session_path), args.api_id, api_hash)
    await client.connect()
    try:
        print('[1/4] Connected:', client.is_connected())
        if not await client.is_user_authorized():
            sent = await client.send_code_request(args.phone)
            print('[2/4] Login code requested. Check Telegram/SMS on your account.')
            code = input('Login code: ').strip()
            try:
                await client.sign_in(phone=args.phone, code=code, phone_code_hash=sent.phone_code_hash)
            except SessionPasswordNeededError:
                password = getpass.getpass('2FA password (hidden): ')
                await client.sign_in(password=password)
        else:
            print('[2/4] Existing session already authorized.')

        me = await client.get_me()
        print('[3/4] Authorized: True')
        print('[4/4] Account:', {
            'id': me.id,
            'username': me.username,
            'first_name': me.first_name,
            'last_name': me.last_name,
            'phone_suffix': (me.phone[-4:] if me.phone else None),
        })
        print('Smoke test PASS. No messages, joins, invites, or member scans were performed.')
        print('Session saved locally at:', str(session_path) + '.session')
    finally:
        await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
