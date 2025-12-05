"""Configuration management for the Cape Worker."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union


@dataclass
class WorkerConfig:
    """Configuration for the Cape Worker.

    Attributes:
        worker_id: Unique identifier for this worker instance
        poll_interval: Number of seconds to wait between polls
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        workflow_timeout: Timeout in seconds for workflow execution
        working_dir: Optional directory to switch to before processing
    """

    worker_id: str
    poll_interval: int = 10
    log_level: str = "INFO"
    workflow_timeout: int = 3600  # 1 hour default
    working_dir: Optional[Union[str, Path]] = None

    def __post_init__(self):
        """Validate configuration values."""
        if not self.worker_id:
            raise ValueError("worker_id cannot be empty")

        if self.poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        if self.workflow_timeout <= 0:
            raise ValueError("workflow_timeout must be positive")

        valid_log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.log_level.upper() not in valid_log_levels:
            raise ValueError(f"log_level must be one of {valid_log_levels}")

        # Normalize log level to uppercase
        self.log_level = self.log_level.upper()

        if self.working_dir is not None:
            working_dir_path = Path(self.working_dir).expanduser()
            if not working_dir_path.is_absolute():
                raise ValueError("--working-dir must be an absolute path")
            self.working_dir = working_dir_path.resolve()
