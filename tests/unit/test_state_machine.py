import pytest

from telegram_workflow.domain.enums import JobState
from telegram_workflow.domain.errors import InvalidStateTransition
from telegram_workflow.domain.state_machine import ensure_job_transition


def test_valid_job_transition() -> None:
    ensure_job_transition(JobState.READY, JobState.RUNNING)
    ensure_job_transition(JobState.RUNNING, JobState.PAUSED)
    ensure_job_transition(JobState.PAUSED, JobState.RUNNING)


def test_terminal_job_cannot_restart() -> None:
    with pytest.raises(InvalidStateTransition):
        ensure_job_transition(JobState.COMPLETED, JobState.RUNNING)
