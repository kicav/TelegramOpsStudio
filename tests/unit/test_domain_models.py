from telegram_workflow.domain.enums import JobMemberState, JobState
from telegram_workflow.domain.models import TelegramMember


def test_member_identity_model() -> None:
    member = TelegramMember(user_id=123, access_hash=456, username="demo")
    assert member.user_id == 123
    assert member.access_hash == 456


def test_states_are_stable_strings() -> None:
    assert JobState.RUNNING.value == "RUNNING"
    assert JobMemberState.RETRY_WAIT.value == "RETRY_WAIT"
