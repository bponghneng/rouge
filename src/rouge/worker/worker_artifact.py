"""Worker artifact type definitions and persistence helpers.

This module provides the WorkerArtifact model and filesystem-backed helpers
for persisting worker state to disk. Worker artifacts track the current state
of a worker daemon instance, including what issue it's processing.
"""

import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return current UTC time in a timezone-aware manner."""
    return datetime.now(timezone.utc)


class WorkerArtifact(BaseModel):
    """Artifact containing worker daemon state.

    Attributes:
        worker_id: The unique identifier for this worker instance
        state: Current worker state (ready, working, or failed)
        current_issue_id: The issue currently being processed (if any)
        current_adw_id: The ADW ID for the current workflow (if any)
        updated_at: Timestamp of last state update
    """

    worker_id: str = Field(
        description="The unique identifier for this worker instance",
        min_length=1,
    )
    state: Literal["ready", "working", "failed"] = Field(
        description="Current worker state",
    )
    current_issue_id: Optional[int] = Field(
        default=None,
        description="The issue ID currently being processed",
    )
    current_adw_id: Optional[str] = Field(
        default=None,
        description="The ADW ID for the current workflow execution",
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        description="Timestamp of last state update",
    )

    def refresh_timestamp(self) -> None:
        """Update the updated_at timestamp to the current UTC time."""
        self.updated_at = _utc_now()


def _get_worker_artifact_path(worker_id: str) -> Path:
    """Get the file path for a worker's state artifact.

    The worker_id must pass strict validation rules:
    - Cannot be empty or contain only whitespace
    - Must match allowlist pattern: [a-zA-Z0-9._-]+
    - Cannot contain path separators (/ or \\)
    - Cannot start or end with dots
    - Resolved path must be contained within workers_root directory

    Args:
        worker_id: The worker identifier

    Returns:
        Path to the worker state JSON file

    Raises:
        ValueError: If worker_id is invalid or attempts path traversal
    """
    from rouge.core.paths import RougePaths

    # Early rejection of empty or whitespace-only worker_id
    if not worker_id or not worker_id.strip():
        raise ValueError("Invalid worker_id: empty or whitespace-only")

    # Normalize whitespace
    worker_id = worker_id.strip()

    # Apply allowlist regex: only alphanumeric, dots, underscores, and hyphens
    if not re.match(r"^[a-zA-Z0-9._-]+$", worker_id):
        raise ValueError(
            f"Invalid worker_id: '{worker_id}' contains disallowed characters "
            "(only alphanumeric, '.', '_', and '-' are permitted)"
        )

    # Explicitly check for path separators
    if "/" in worker_id or "\\" in worker_id:
        raise ValueError(f"Invalid worker_id: '{worker_id}' contains path separators")

    # Check for leading or trailing dots
    if worker_id.startswith(".") or worker_id.endswith("."):
        raise ValueError(f"Invalid worker_id: '{worker_id}' starts or ends with a dot")

    base_dir = RougePaths.get_base_dir()
    workers_root = base_dir / "workers"

    # Resolve paths to validate containment
    workers_root_resolved = workers_root.resolve()
    candidate_worker_dir = (workers_root / worker_id).resolve()

    # Validate that candidate_worker_dir is a descendant of workers_root
    try:
        candidate_worker_dir.relative_to(workers_root_resolved)
    except ValueError:
        raise ValueError(f"Invalid worker_id: '{worker_id}' resolves outside workers directory")

    return candidate_worker_dir / "state.json"


def read_worker_artifact(worker_id: str) -> Optional[WorkerArtifact]:
    """Read a worker artifact from disk.

    Args:
        worker_id: The worker identifier

    Returns:
        The deserialized WorkerArtifact, or None if not found or invalid
    """
    try:
        artifact_path = _get_worker_artifact_path(worker_id)
    except ValueError as e:
        logger.warning("Invalid worker_id for read: %s", e)
        return None

    if not artifact_path.exists():
        logger.debug("Worker artifact not found: %s", artifact_path)
        return None

    try:
        json_data = artifact_path.read_text(encoding="utf-8")
        artifact = WorkerArtifact.model_validate_json(json_data)
        logger.debug("Read worker artifact for %s from %s", worker_id, artifact_path)
        return artifact
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse worker artifact for %s: %s", worker_id, e)
        return None
    except Exception as e:
        logger.warning("Failed to read worker artifact for %s: %s", worker_id, e)
        return None


def write_worker_artifact(artifact: WorkerArtifact) -> None:
    """Write a worker artifact to disk.

    This is a best-effort operation that will not raise exceptions.
    Failures are logged but do not halt execution.

    Args:
        artifact: The WorkerArtifact to persist
    """
    try:
        artifact_path = _get_worker_artifact_path(artifact.worker_id)
    except ValueError as e:
        logger.warning("Invalid worker_id for write: %s", e)
        return

    temp_path = None
    try:
        # Ensure the worker directory exists
        artifact_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        json_data = artifact.model_dump_json(indent=2)

        # Create temp file in artifact_path.parent with suffix ".tmp"
        fd, temp_path_str = tempfile.mkstemp(suffix=".tmp", dir=artifact_path.parent)
        temp_path = Path(temp_path_str)

        try:
            # Write JSON to temp file, flush and fsync file descriptor
            os.write(fd, json_data.encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)

        # Set mode to 0o600 on temp file
        os.chmod(temp_path, 0o600)

        # Use os.replace for atomic replacement
        os.replace(temp_path, artifact_path)

        # Only log success after atomic replace completes
        logger.debug("Wrote worker artifact for %s to %s", artifact.worker_id, artifact_path)
    except Exception as e:
        # Best-effort: log but don't raise
        # Clean up temp file on failure
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass  # Ignore cleanup errors
        logger.warning("Failed to write worker artifact for %s: %s", artifact.worker_id, e)
