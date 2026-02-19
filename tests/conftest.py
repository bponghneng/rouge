"""Shared pytest fixtures for Rouge tests."""

from pathlib import Path

import pytest

from rouge.core.workflow.artifacts import ArtifactStore


@pytest.fixture
def tmp_artifact_store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary ArtifactStore for testing.

    This fixture provides a temporary artifact store that uses pytest's tmp_path
    fixture for isolated test execution. Each test receives a unique temporary
    directory that is automatically cleaned up after the test completes.

    Args:
        tmp_path: pytest's built-in temporary directory fixture

    Returns:
        ArtifactStore instance configured to use tmp_path

    Example:
        def test_something(tmp_artifact_store):
            ctx = WorkflowContext(
                adw_id="test-adw",
                issue_id=1,
                artifact_store=tmp_artifact_store
            )
    """
    return ArtifactStore(workflow_id="test-workflow", base_path=tmp_path)
