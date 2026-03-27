"""Unit tests for WorkflowStateArtifact."""

import json
from datetime import datetime

import pytest

from rouge.core.workflow.artifacts import (
    ARTIFACT_MODELS,
    ArtifactStore,
    WorkflowStateArtifact,
)


class TestWorkflowStateArtifactModel:
    """Tests for WorkflowStateArtifact model definition."""

    def test_artifact_creation_with_all_fields(self):
        """Test WorkflowStateArtifact can be created with all fields."""
        artifact = WorkflowStateArtifact(
            workflow_id="adw-123",
            pipeline_type="adw",
            last_completed_step="plan",
            failed_step="implement",
        )

        assert artifact.workflow_id == "adw-123"
        assert artifact.artifact_type == "workflow-state"
        assert artifact.pipeline_type == "adw"
        assert artifact.last_completed_step == "plan"
        assert artifact.failed_step == "implement"
        assert isinstance(artifact.created_at, datetime)

    def test_artifact_creation_with_minimal_fields(self):
        """Test WorkflowStateArtifact with only required fields."""
        artifact = WorkflowStateArtifact(
            workflow_id="adw-456",
            pipeline_type="patch",
        )

        assert artifact.workflow_id == "adw-456"
        assert artifact.artifact_type == "workflow-state"
        assert artifact.pipeline_type == "patch"
        assert artifact.last_completed_step is None
        assert artifact.failed_step is None

    def test_artifact_creation_with_last_completed_only(self):
        """Test WorkflowStateArtifact with last_completed_step but no failed_step."""
        artifact = WorkflowStateArtifact(
            workflow_id="adw-789",
            pipeline_type="adw",
            last_completed_step="classify",
        )

        assert artifact.last_completed_step == "classify"
        assert artifact.failed_step is None

    def test_artifact_creation_with_failed_only(self):
        """Test WorkflowStateArtifact with failed_step but no last_completed_step."""
        artifact = WorkflowStateArtifact(
            workflow_id="adw-999",
            pipeline_type="main",
            failed_step="code-quality",
        )

        assert artifact.last_completed_step is None
        assert artifact.failed_step == "code-quality"

    def test_artifact_type_is_correct(self):
        """Test artifact_type is set to 'workflow-state'."""
        artifact = WorkflowStateArtifact(
            workflow_id="adw-test",
            pipeline_type="adw",
        )

        assert artifact.artifact_type == "workflow-state"

    def test_pipeline_type_validation(self):
        """Test pipeline_type field validation."""
        # Valid pipeline types
        artifact = WorkflowStateArtifact(
            workflow_id="adw-test",
            pipeline_type="adw",
        )
        assert artifact.pipeline_type == "adw"

        artifact = WorkflowStateArtifact(
            workflow_id="adw-test",
            pipeline_type="patch",
        )
        assert artifact.pipeline_type == "patch"

        artifact = WorkflowStateArtifact(
            workflow_id="adw-test",
            pipeline_type="full",
        )
        assert artifact.pipeline_type == "full"

    def test_empty_pipeline_type_fails(self):
        """Test that empty pipeline_type fails validation."""
        with pytest.raises(ValueError, match="at least 1 character"):
            WorkflowStateArtifact(
                workflow_id="adw-test",
                pipeline_type="",
            )


class TestWorkflowStateArtifactSerialization:
    """Tests for WorkflowStateArtifact JSON serialization/deserialization."""

    def test_artifact_round_trip_with_all_fields(self):
        """Test artifact can be serialized and deserialized with all fields."""
        original = WorkflowStateArtifact(
            workflow_id="adw-rt-123",
            pipeline_type="adw",
            last_completed_step="plan",
            failed_step="implement",
        )

        json_str = original.model_dump_json()
        restored = WorkflowStateArtifact.model_validate_json(json_str)

        assert restored.workflow_id == "adw-rt-123"
        assert restored.artifact_type == "workflow-state"
        assert restored.pipeline_type == "adw"
        assert restored.last_completed_step == "plan"
        assert restored.failed_step == "implement"

    def test_artifact_round_trip_with_minimal_fields(self):
        """Test artifact serialization with only required fields."""
        original = WorkflowStateArtifact(
            workflow_id="adw-rt-456",
            pipeline_type="patch",
        )

        json_str = original.model_dump_json()
        restored = WorkflowStateArtifact.model_validate_json(json_str)

        assert restored.workflow_id == "adw-rt-456"
        assert restored.pipeline_type == "patch"
        assert restored.last_completed_step is None
        assert restored.failed_step is None

    def test_json_structure_is_valid(self):
        """Test artifact JSON has expected structure."""
        artifact = WorkflowStateArtifact(
            workflow_id="adw-json-test",
            pipeline_type="adw",
            last_completed_step="classify",
            failed_step="plan",
        )

        json_str = artifact.model_dump_json(indent=2)
        parsed = json.loads(json_str)

        assert "workflow_id" in parsed
        assert "artifact_type" in parsed
        assert "pipeline_type" in parsed
        assert "last_completed_step" in parsed
        assert "failed_step" in parsed
        assert "created_at" in parsed
        assert parsed["artifact_type"] == "workflow-state"
        assert parsed["workflow_id"] == "adw-json-test"
        assert parsed["pipeline_type"] == "adw"
        assert parsed["last_completed_step"] == "classify"
        assert parsed["failed_step"] == "plan"

    def test_json_with_none_values(self):
        """Test artifact JSON correctly handles None values."""
        artifact = WorkflowStateArtifact(
            workflow_id="adw-none-test",
            pipeline_type="patch",
        )

        json_str = artifact.model_dump_json()
        parsed = json.loads(json_str)

        assert parsed["last_completed_step"] is None
        assert parsed["failed_step"] is None


class TestWorkflowStateArtifactInStore:
    """Tests for WorkflowStateArtifact integration with ArtifactStore."""

    def test_write_workflow_state_artifact(self, tmp_path):
        """Test writing workflow state artifact to disk."""
        store = ArtifactStore("adw-write-test", base_path=tmp_path)
        artifact = WorkflowStateArtifact(
            workflow_id="adw-write-test",
            pipeline_type="adw",
            last_completed_step="plan",
            failed_step="implement",
        )

        store.write_artifact(artifact)

        artifact_path = tmp_path / "adw-write-test" / "workflow-state.json"
        assert artifact_path.exists()

        # Verify content
        content = json.loads(artifact_path.read_text())
        assert content["artifact_type"] == "workflow-state"
        assert content["pipeline_type"] == "adw"
        assert content["last_completed_step"] == "plan"
        assert content["failed_step"] == "implement"

    def test_read_workflow_state_artifact(self, tmp_path):
        """Test reading workflow state artifact from disk."""
        store = ArtifactStore("adw-read-test", base_path=tmp_path)
        original = WorkflowStateArtifact(
            workflow_id="adw-read-test",
            pipeline_type="patch",
            last_completed_step="fetch-patch",
            failed_step="code-quality",
        )

        store.write_artifact(original)
        restored = store.read_artifact("workflow-state", WorkflowStateArtifact)

        assert restored.workflow_id == "adw-read-test"
        assert restored.pipeline_type == "patch"
        assert restored.last_completed_step == "fetch-patch"
        assert restored.failed_step == "code-quality"

    def test_read_workflow_state_auto_detects_model(self, tmp_path):
        """Test read_artifact auto-detects WorkflowStateArtifact model."""
        store = ArtifactStore("adw-auto-detect", base_path=tmp_path)
        artifact = WorkflowStateArtifact(
            workflow_id="adw-auto-detect",
            pipeline_type="adw",
            last_completed_step="classify",
        )
        store.write_artifact(artifact)

        # Read without specifying model class
        restored = store.read_artifact("workflow-state")

        assert isinstance(restored, WorkflowStateArtifact)
        assert restored.workflow_id == "adw-auto-detect"
        assert restored.pipeline_type == "adw"
        assert restored.last_completed_step == "classify"

    def test_workflow_state_artifact_exists(self, tmp_path):
        """Test artifact_exists returns True for workflow-state."""
        store = ArtifactStore("adw-exists", base_path=tmp_path)
        artifact = WorkflowStateArtifact(
            workflow_id="adw-exists",
            pipeline_type="adw",
        )
        store.write_artifact(artifact)

        assert store.artifact_exists("workflow-state") is True

    def test_workflow_state_artifact_not_exists(self, tmp_path):
        """Test artifact_exists returns False when workflow-state is missing."""
        store = ArtifactStore("adw-no-exists", base_path=tmp_path)

        assert store.artifact_exists("workflow-state") is False

    def test_overwrite_workflow_state_artifact(self, tmp_path):
        """Test overwriting an existing workflow state artifact."""
        store = ArtifactStore("adw-overwrite", base_path=tmp_path)

        # Write initial artifact
        artifact1 = WorkflowStateArtifact(
            workflow_id="adw-overwrite",
            pipeline_type="adw",
            last_completed_step="plan",
        )
        store.write_artifact(artifact1)

        # Overwrite with new artifact
        artifact2 = WorkflowStateArtifact(
            workflow_id="adw-overwrite",
            pipeline_type="adw",
            last_completed_step="implement",
            failed_step="code-quality",
        )
        store.write_artifact(artifact2)

        # Read back should get second version
        restored = store.read_artifact("workflow-state")
        assert restored.last_completed_step == "implement"
        assert restored.failed_step == "code-quality"

    def test_list_artifacts_includes_workflow_state(self, tmp_path):
        """Test list_artifacts includes workflow-state."""
        store = ArtifactStore("adw-list", base_path=tmp_path)

        # Write workflow state artifact
        artifact = WorkflowStateArtifact(
            workflow_id="adw-list",
            pipeline_type="adw",
        )
        store.write_artifact(artifact)

        artifacts = store.list_artifacts()
        assert "workflow-state" in artifacts

    def test_delete_workflow_state_artifact(self, tmp_path):
        """Test deleting workflow state artifact."""
        store = ArtifactStore("adw-delete", base_path=tmp_path)
        artifact = WorkflowStateArtifact(
            workflow_id="adw-delete",
            pipeline_type="adw",
        )
        store.write_artifact(artifact)

        assert store.artifact_exists("workflow-state") is True

        result = store.delete_artifact("workflow-state")

        assert result is True
        assert store.artifact_exists("workflow-state") is False


class TestArtifactModelsMapping:
    """Tests for ARTIFACT_MODELS mapping includes workflow-state."""

    def test_workflow_state_in_artifact_models(self):
        """Test ARTIFACT_MODELS contains workflow-state."""
        assert "workflow-state" in ARTIFACT_MODELS

    def test_workflow_state_maps_to_correct_class(self):
        """Test workflow-state maps to WorkflowStateArtifact."""
        assert ARTIFACT_MODELS["workflow-state"] == WorkflowStateArtifact
