class WorkflowError(Exception):
    """Base domain error."""


class DatabaseMigrationError(WorkflowError):
    """Raised when a database migration cannot be applied safely."""


class InvalidStateTransition(WorkflowError):
    """Raised when a state machine transition is not allowed."""


class SourceUnavailableError(WorkflowError):
    """Raised when a source cannot be resolved or scanned lawfully."""


class TargetValidationError(WorkflowError):
    """Raised when the target is invalid or lacks required permissions."""


class LiveActionDisabledError(WorkflowError):
    """Raised when a live membership action is intentionally disabled."""
