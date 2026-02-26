"""Worker artifact type definitions and persistence helpers.

This module provides the WorkerArtifact model and filesystem-backed helpers
for persisting worker state to disk. Worker artifacts track the current state
of a worker daemon instance, including what issue it's processing.
"""

import json
import logging
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

    Args:
        worker_id: The worker identifier

    Returns:
        Path to the worker state JSON file
    """
    from rouge.core.paths import RougePaths

    base_dir = RougePaths.get_base_dir()
    worker_dir = base_dir / "workers" / worker_id
    return worker_dir / "state.json"


def read_worker_artifact(worker_id: str) -> Optional[WorkerArtifact]:
    """Read a worker artifact from disk.

    Args:
        worker_id: The worker identifier

    Returns:
        The deserialized WorkerArtifact, or None if not found or invalid
    """
    artifact_path = _get_worker_artifact_path(worker_id)

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
    artifact_path = _get_worker_artifact_path(artifact.worker_id)

    try:
        # Ensure the worker directory exists
        artifact_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)

        json_data = artifact.model_dump_json(indent=2)
        artifact_path.write_text(json_data, encoding="utf-8")
        logger.debug("Wrote worker artifact for %s to %s", artifact.worker_id, artifact_path)
    except Exception as e:
        # Best-effort: log but don't raise
        logger.warning("Failed to write worker artifact for %s: %s", artifact.worker_id, e)
