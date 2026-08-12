class WorkflowError(Exception):
    """Base domain error."""


class DatabaseMigrationError(WorkflowError):
    """Raised when a database migration cannot be applied safely."""
