"""Configuration management for the Rouge Worker."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class WorkerConfig:
    """Configuration for the Rouge Worker.

    Attributes:
        worker_id: Unique identifier for this worker instance
        poll_interval: Number of seconds to wait between polls
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        workflow_timeout: Timeout in seconds for workflow execution
        working_dir: Optional directory to run worker from
        db_retries: Number of retry attempts for database operations
        db_backoff_ms: Backoff delay in milliseconds between retry attempts
    """

    worker_id: str
    poll_interval: int = 10
    log_level: str = "INFO"
    workflow_timeout: int = 3600  # 1 hour default
    working_dir: Optional[str] = None
    db_retries: int = 3
    db_backoff_ms: int = 500

    def __post_init__(self):
        """Validate configuration values."""
        # Check for leading/trailing whitespace
        if self.worker_id != self.worker_id.strip():
            raise ValueError("worker_id cannot have leading or trailing whitespace")

        # Reject any whitespace characters
        if any(c.isspace() for c in self.worker_id):
            raise ValueError("worker_id cannot contain whitespace characters")

        if not self.worker_id or not self.worker_id.strip():
            raise ValueError("worker_id cannot be empty or whitespace-only")

        # Validate worker_id to prevent path traversal
        if "/" in self.worker_id or "\\" in self.worker_id:
            raise ValueError("worker_id cannot contain path separators")

        if os.path.pardir in self.worker_id:
            raise ValueError("worker_id cannot contain parent directory references")

        parts = Path(self.worker_id).parts
        if len(parts) != 1:
            raise ValueError("worker_id must be a single path component")

        if parts[0] in (".", ".."):
            raise ValueError("worker_id cannot be '.' or '..'")

        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        if self.workflow_timeout <= 0:
            raise ValueError("workflow_timeout must be positive")

        if self.db_retries <= 0:
            raise ValueError("db_retries must be positive")

        if self.db_backoff_ms <= 0:
            raise ValueError("db_backoff_ms must be positive")

        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(f"log_level must be one of {valid_log_levels}")

        # Normalize log level to uppercase
        self.log_level = self.log_level.upper()
