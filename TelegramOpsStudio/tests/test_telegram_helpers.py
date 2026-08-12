from __future__ import annotations

import pytest

pytest.importorskip("telethon")
pytest.importorskip("socks")

from app.telegram_service import invite_hash


def test_invite_hash_parsing():
    assert invite_hash("https://t.me/+ABC123") == "ABC123"
    assert invite_hash("https://t.me/joinchat/XYZ") == "XYZ"
    assert invite_hash("@public_group") is None
