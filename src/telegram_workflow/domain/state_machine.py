from __future__ import annotations

from telegram_workflow.domain.enums import JobState
from telegram_workflow.domain.errors import InvalidStateTransition

_ALLOWED_JOB_TRANSITIONS: dict[JobState, set[JobState]] = {
    JobState.DRAFT: {JobState.VALIDATING, JobState.READY, JobState.CANCELLED},
    JobState.VALIDATING: {JobState.READY, JobState.FAILED, JobState.CANCELLED},
    JobState.READY: {JobState.RUNNING, JobState.CANCELLED, JobState.FAILED},
    JobState.RUNNING: {
        JobState.PAUSING,
        JobState.PAUSED,
        JobState.CANCELLING,
        JobState.COMPLETING,
        JobState.COMPLETED,
        JobState.FAILED,
    },
    JobState.PAUSING: {JobState.PAUSED, JobState.FAILED},
    JobState.PAUSED: {JobState.RUNNING, JobState.CANCELLING, JobState.CANCELLED, JobState.FAILED},
    JobState.CANCELLING: {JobState.CANCELLED, JobState.FAILED},
    JobState.COMPLETING: {JobState.COMPLETED, JobState.FAILED},
    JobState.CANCELLED: set(),
    JobState.COMPLETED: set(),
    JobState.FAILED: set(),
}


def ensure_job_transition(current: JobState, target: JobState) -> None:
    if current == target:
        return
    if target not in _ALLOWED_JOB_TRANSITIONS[current]:
        raise InvalidStateTransition(
            f"Job transition {current.value} -> {target.value} is not allowed"
        )
