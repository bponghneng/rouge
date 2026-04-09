"""Utility functions for Rouge CLI workflow system."""

import logging
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


def make_adw_id() -> str:
    """Generate a short 8-character UUID for workflow tracking."""
    return str(uuid.uuid4())[:8]


def _get_log_level() -> int:
    """Get log level from ROUGE_LOG_LEVEL environment variable.

    Supports: DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive).
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
        "CRITICAL": logging.CRITICAL,
    }
    return level_map.get(level_str, logging.INFO)


def setup_logger(
    adw_id: str,
    trigger_type: str = "adw_plan_build",
    detached_mode: bool = False,
) -> logging.Logger:
    """Set up logger that writes to both console and file using adw_id.

    Log level is configurable via ROUGE_LOG_LEVEL environment variable.
    Supported values: DEBUG, INFO, WARNING, ERROR, CRITICAL (case-insensitive).
    Default: INFO.

    Args:
        adw_id: The workflow ID
        trigger_type: Logical source of the run (e.g., adw_plan_build)
        detached_mode: If True, disable console handler (for background processes)

    Returns:
        Configured logger instance
    """
    # Create log directory: .rouge/agents/logs/{adw_id}/{trigger_type}/
    from rouge.core.workflow.shared import get_working_dir

    agents_log_dir = Path(get_working_dir()) / ".rouge/agents/logs"
    log_dir = str(agents_log_dir / adw_id / trigger_type)

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
    logger.info("Rouge Logger initialized - ID: %s (detached=%s)", adw_id, detached_mode)
    logger.debug("Log file: %s", log_file)

    return logger


def get_logger(adw_id: str) -> logging.Logger:
    """Get existing logger by workflow ID.

    Args:
        adw_id: The workflow ID

    Returns:
        Logger instance

    Raises:
        ValueError: If adw_id is empty or None
    """
    if not adw_id:
        raise ValueError("adw_id must be a non-empty string")
    return logging.getLogger(f"rouge_{adw_id}")


def extract_repo_from_pull_request_url(url: Any) -> str | None:
    """Extract owner/repo (or group/project) from a PR/MR URL."""
    if not isinstance(url, str) or not url:
        return None

    parsed = urlparse(url)
    path_parts = [part for part in parsed.path.split("/") if part]
    if not path_parts:
        return None

    if "pull" in path_parts:
        marker_index = path_parts.index("pull")
        repo_parts = path_parts[:marker_index]
    elif "-" in path_parts:
        marker_index = path_parts.index("-")
        repo_parts = path_parts[:marker_index]
    else:
        repo_parts = path_parts[:2]

    if len(repo_parts) < 2:
        return None
    return "/".join(repo_parts)
