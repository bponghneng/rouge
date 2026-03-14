"""Worker-specific exception types for error handling and retry logic."""


class TransientDatabaseError(Exception):
    """Raised when a transient database error occurs.

    Transient database errors include timeout, connection errors, or stale
    keep-alive connections that should trigger retry/backoff logic without
    halting the worker daemon. These errors are expected to resolve on retry
    after the database client is reset.

    Attributes:
        message: Human-readable error description
        original_error: The underlying exception that triggered this error
    """

    def __init__(self, message: str, original_error: Exception) -> None:
        """Initialize TransientDatabaseError.

        Args:
            message: Description of the transient database error
            original_error: The original exception that was caught
        """
        super().__init__(message)
        self.message = message
        self.original_error = original_error

    def __str__(self) -> str:
        """Return string representation including original error."""
        error_type = type(self.original_error).__name__
        return f"{self.message} (caused by {error_type}: {self.original_error})"
