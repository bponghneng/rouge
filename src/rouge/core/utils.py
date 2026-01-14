"""Utility functions for Rouge CLI workflow system."""

import logging
import os
import sys
import uuid
from logging import Handler
from logging.handlers import RotatingFileHandler
from typing import Optional


def make_adw_id() -> str:
    """Generate a short 8-character UUID for workflow tracking."""
    return str(uuid.uuid4())[:8]


def make_patch_workflow_id(main_adw_id: str) -> str:
    """Derive a patch workflow ID from a main ADW workflow ID.

    Patch workflows need a separate workflow ID to isolate their artifacts
    (logs, plans, implementation outputs) from the main workflow artifacts.
    This prevents collision and allows both workflows to maintain independent
    state in the artifact store.

    Args:
        main_adw_id: The main ADW workflow ID to derive from

    Returns:
        A derived workflow ID in the format "{main_adw_id}-patch"
    """
    return f"{main_adw_id}-patch"


def _get_log_level() -> int:
    """Get log level from ROUGE_LOG_LEVEL environment variable.

    Supports: DEBUG, INFO, WARNING, ERROR (case-insensitive).
    Defaults to INFO if not set or invalid.

    Returns:
        Logging level constant
    """
    level_str = os.environ.get("ROUGE_LOG_LEVEL", "INFO").upper()
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    return level_map.get(level_str, logging.INFO)


def setup_logger(
    adw_id: str,
    trigger_type: str = "adw_plan_build",
    detached_mode: bool = False,
    use_rotating: bool = False,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """Set up logger that writes to both console and file using adw_id.

    Log level is configurable via ROUGE_LOG_LEVEL environment variable.
    Supported values: DEBUG, INFO, WARNING, ERROR (case-insensitive).
    Default: INFO.

    Args:
        adw_id: The workflow ID
        trigger_type: Logical source of the run (e.g., adw_plan_build)
        detached_mode: If True, disable console handler (for background processes)
        use_rotating: If True, use RotatingFileHandler instead of FileHandler
        max_bytes: Maximum file size before rotation (only if use_rotating=True)
        backup_count: Number of backup files to keep (only if use_rotating=True)

    Returns:
        Configured logger instance
    """
    # Create log directory: .rouge/logs/agents/{adw_id}/{trigger_type}/
    # Use current working directory as base or environment variable override
    agents_dir = os.environ.get("ROUGE_AGENTS_DIR", os.path.join(os.getcwd(), ".rouge/logs/agents"))
    log_dir = os.path.join(agents_dir, adw_id, trigger_type)

    # Atomic directory creation with proper error handling
    try:
        os.makedirs(log_dir, exist_ok=True, mode=0o755)
    except FileExistsError:
        # Race condition - directory was created by another process
        pass

    # Log file path: .rouge/logs/agents/{adw_id}/{trigger_type}/execution.log
    log_file = os.path.join(log_dir, "execution.log")

    # Create logger with unique name using adw_id
    logger = logging.getLogger(f"rouge_{adw_id}")
    logger.setLevel(logging.DEBUG)

    # Clear any existing handlers to avoid duplicates
    logger.handlers.clear()

    # File handler - captures everything
    file_handler: Handler
    if use_rotating:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backup_count, mode="a"
        )
    else:
        file_handler = logging.FileHandler(log_file, mode="a")

    file_handler.setLevel(logging.DEBUG)

    # Format with timestamp for file
    file_formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler - only if not in detached mode
    # Uses ROUGE_LOG_LEVEL for console output (file always captures DEBUG)
    if not detached_mode:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(_get_log_level())

        # Simpler format for console
        console_formatter = logging.Formatter("%(message)s")
        console_handler.setFormatter(console_formatter)

        logger.addHandler(console_handler)

    # Log initial setup message
    logger.info(f"Rouge Logger initialized - ID: {adw_id} (detached={detached_mode})")
    logger.debug(f"Log file: {log_file}")

    return logger


def get_logger(adw_id: str) -> logging.Logger:
    """Get existing logger by workflow ID.

    Args:
        adw_id: The workflow ID

    Returns:
        Logger instance
    """
    return logging.getLogger(f"rouge_{adw_id}")


def log_workflow_event(
    logger: logging.Logger, step: str, status: str, details: Optional[str] = None
) -> None:
    """Log a structured workflow event.

    Args:
        logger: Logger instance to use
        step: Workflow step name (e.g., "classify", "plan", "implement")
        status: Event status (e.g., "started", "completed", "failed")
        details: Optional additional details
    """
    message = f"[{step}] {status}"
    if details:
        message += f" - {details}"

    if status == "failed":
        logger.error(message)
    elif status in ("started", "initializing"):
        logger.info(message)
    elif status in ("completed", "stopped"):
        logger.info(message)
    else:
        logger.debug(message)
