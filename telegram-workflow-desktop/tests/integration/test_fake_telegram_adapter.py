import asyncio

from telegram_workflow.domain.models import TelegramMember
from tests.fakes.fake_telegram_adapter import FakeTelegramAdapter


def test_fake_adapter_is_deterministic() -> None:
    async def scenario() -> None:
        adapter = FakeTelegramAdapter([TelegramMember(user_id=1), TelegramMember(user_id=2)])
        assert await adapter.health_check() is True
        entity = await adapter.resolve_entity("source")
        members = [member async for member in adapter.iter_accessible_members(entity)]
        assert [member.user_id for member in members] == [1, 2]
        validation = await adapter.validate_target(entity)
        assert validation.ready is True

    asyncio.run(scenario())
