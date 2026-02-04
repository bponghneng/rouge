"""Unit tests for workflow artifact persistence layer."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import (
    ARTIFACT_MODELS,
    AcceptanceArtifact,
    ArtifactStore,
    ClassificationArtifact,
    ImplementationArtifact,
    IssueArtifact,
    PlanArtifact,
    PRMetadataArtifact,
    PullRequestArtifact,
    QualityCheckArtifact,
    ReviewAddressedArtifact,
    ReviewArtifact,
)
from rouge.core.workflow.types import (
    ClassifyData,
    ImplementData,
    PlanData,
    ReviewData,
)


class TestArtifactModels:
    """Tests for artifact model definitions."""

    def test_issue_artifact_creation(self):
        """Test IssueArtifact can be created with valid data."""
        issue = Issue(id=1, description="Test issue")
        artifact = IssueArtifact(
            workflow_id="adw-123",
            issue=issue,
        )

        assert artifact.workflow_id == "adw-123"
        assert artifact.artifact_type == "issue"
        assert artifact.issue.id == 1
        assert artifact.issue.description == "Test issue"
        assert isinstance(artifact.created_at, datetime)

    def test_classification_artifact_creation(self):
        """Test ClassificationArtifact can be created with valid data."""
        classify_data = ClassifyData(
            command="/adw-feature-plan",
            classification={"type": "feature", "level": "medium"},
        )
        artifact = ClassificationArtifact(
            workflow_id="adw-123",
            classify_data=classify_data,
        )

        assert artifact.artifact_type == "classification"
        assert artifact.classify_data.command == "/adw-feature-plan"
        assert artifact.classify_data.classification["type"] == "feature"

    def test_plan_artifact_creation(self):
        """Test PlanArtifact can be created with valid data."""
        plan_data = PlanData(
            plan="Plan content here", summary="Plan summary", session_id="session-456"
        )
        artifact = PlanArtifact(
            workflow_id="adw-123",
            plan_data=plan_data,
        )

        assert artifact.artifact_type == "plan"
        assert artifact.plan_data.plan == "Plan content here"
        assert artifact.plan_data.summary == "Plan summary"
        assert artifact.plan_data.session_id == "session-456"

    def test_implementation_artifact_creation(self):
        """Test ImplementationArtifact can be created with valid data."""
        implement_data = ImplementData(output="Implementation output")
        artifact = ImplementationArtifact(
            workflow_id="adw-123",
            implement_data=implement_data,
        )

        assert artifact.artifact_type == "implementation"
        assert artifact.implement_data.output == "Implementation output"

    def test_review_artifact_creation(self):
        """Test ReviewArtifact can be created with valid data."""
        review_data = ReviewData(
            review_text="Code review content",
        )
        artifact = ReviewArtifact(
            workflow_id="adw-123",
            review_data=review_data,
        )

        assert artifact.artifact_type == "review"
        assert artifact.review_data.review_text == "Code review content"

    def test_review_addressed_artifact_creation(self):
        """Test ReviewAddressedArtifact can be created with valid data."""
        artifact = ReviewAddressedArtifact(
            workflow_id="adw-123",
            success=True,
            message="All issues resolved",
        )

        assert artifact.artifact_type == "review_addressed"
        assert artifact.success is True
        assert artifact.message == "All issues resolved"

    def test_quality_check_artifact_creation(self):
        """Test QualityCheckArtifact can be created with valid data."""
        artifact = QualityCheckArtifact(
            workflow_id="adw-123",
            output="Quality check output",
            tools=["ruff", "mypy"],
            parsed_data={"issues": 0},
        )

        assert artifact.artifact_type == "quality_check"
        assert artifact.output == "Quality check output"
        assert artifact.tools == ["ruff", "mypy"]
        assert artifact.parsed_data == {"issues": 0}

    def test_acceptance_artifact_creation(self):
        """Test AcceptanceArtifact can be created with valid data."""
        artifact = AcceptanceArtifact(
            workflow_id="adw-123",
            success=True,
            message="Implementation accepted",
        )

        assert artifact.artifact_type == "acceptance"
        assert artifact.success is True
        assert artifact.message == "Implementation accepted"

    def test_pr_metadata_artifact_creation(self):
        """Test PRMetadataArtifact can be created with valid data."""
        artifact = PRMetadataArtifact(
            workflow_id="adw-123",
            title="Add new feature",
            summary="This PR adds a new feature",
            commits=[{"sha": "abc123", "message": "feat: add feature"}],
        )

        assert artifact.artifact_type == "pr_metadata"
        assert artifact.title == "Add new feature"
        assert artifact.summary == "This PR adds a new feature"
        assert len(artifact.commits) == 1
        assert artifact.commits[0]["sha"] == "abc123"

    def test_pull_request_artifact_creation(self):
        """Test PullRequestArtifact can be created with valid data."""
        artifact = PullRequestArtifact(
            workflow_id="adw-123",
            url="https://github.com/org/repo/pull/42",
            platform="github",
        )

        assert artifact.artifact_type == "pull_request"
        assert artifact.url == "https://github.com/org/repo/pull/42"
        assert artifact.platform == "github"

    def test_artifact_models_mapping_complete(self):
        """Test ARTIFACT_MODELS contains all expected types."""
        expected_types = {
            "issue",
            "classification",
            "plan",
            "implementation",
            "review",
            "review_addressed",
            "quality_check",
            "acceptance",
            "pr_metadata",
            "pull_request",
            "patch",
        }

        assert set(ARTIFACT_MODELS.keys()) == expected_types


class TestArtifactSerialization:
    """Tests for artifact JSON serialization/deserialization."""

    def test_issue_artifact_round_trip(self):
        """Test IssueArtifact can be serialized and deserialized."""
        issue = Issue(id=42, description="Test issue for round trip")
        artifact = IssueArtifact(
            workflow_id="adw-test",
            issue=issue,
        )

        json_str = artifact.model_dump_json()
        restored = IssueArtifact.model_validate_json(json_str)

        assert restored.workflow_id == artifact.workflow_id
        assert restored.artifact_type == "issue"
        assert restored.issue.id == 42
        assert restored.issue.description == "Test issue for round trip"

    def test_classification_artifact_round_trip(self):
        """Test ClassificationArtifact can be serialized and deserialized."""
        classify_data = ClassifyData(
            command="/adw-bug-plan",
            classification={"type": "bug", "level": "high"},
        )
        artifact = ClassificationArtifact(
            workflow_id="adw-test",
            classify_data=classify_data,
        )

        json_str = artifact.model_dump_json()
        restored = ClassificationArtifact.model_validate_json(json_str)

        assert restored.classify_data.command == "/adw-bug-plan"
        assert restored.classify_data.classification["type"] == "bug"

    def test_artifact_json_is_valid(self):
        """Test artifact JSON is valid and human-readable."""
        issue = Issue(id=1, description="Test")
        artifact = IssueArtifact(workflow_id="adw-123", issue=issue)

        json_str = artifact.model_dump_json(indent=2)
        parsed = json.loads(json_str)

        assert "workflow_id" in parsed
        assert "artifact_type" in parsed
        assert "issue" in parsed
        assert parsed["artifact_type"] == "issue"


class TestArtifactStore:
    """Tests for ArtifactStore filesystem operations."""

    def test_store_initialization_creates_directory(self, tmp_path):
        """Test ArtifactStore creates workflow directory on init."""
        store = ArtifactStore("adw-test-123", base_path=tmp_path)

        assert store.workflow_id == "adw-test-123"
        assert store.workflow_dir == tmp_path / "adw-test-123"
        assert store.workflow_dir.exists()
        assert store.workflow_dir.is_dir()

    def test_store_initialization_with_rouge_paths(self, tmp_path):
        """Test ArtifactStore uses RougePaths.get_workflows_dir() by default."""
        with patch("rouge.core.paths.get_working_dir", return_value=str(tmp_path)):
            store = ArtifactStore("adw-default-123")

            assert store.workflow_dir == tmp_path / ".rouge" / "workflows" / "adw-default-123"
            assert store.workflow_dir.exists()

    def test_write_artifact(self, tmp_path):
        """Test writing an artifact to disk."""
        store = ArtifactStore("adw-write-test", base_path=tmp_path)
        issue = Issue(id=1, description="Test issue")
        artifact = IssueArtifact(workflow_id="adw-write-test", issue=issue)

        store.write_artifact(artifact)

        artifact_path = tmp_path / "adw-write-test" / "issue.json"
        assert artifact_path.exists()

        # Verify content
        content = json.loads(artifact_path.read_text())
        assert content["artifact_type"] == "issue"
        assert content["issue"]["id"] == 1

    def test_read_artifact(self, tmp_path):
        """Test reading an artifact from disk."""
        store = ArtifactStore("adw-read-test", base_path=tmp_path)
        issue = Issue(id=42, description="Read test issue")
        original = IssueArtifact(workflow_id="adw-read-test", issue=issue)

        store.write_artifact(original)
        restored = store.read_artifact("issue", IssueArtifact)

        assert restored.workflow_id == "adw-read-test"
        assert restored.issue.id == 42
        assert restored.issue.description == "Read test issue"

    def test_read_artifact_auto_detects_model(self, tmp_path):
        """Test read_artifact auto-detects model class from artifact type."""
        store = ArtifactStore("adw-auto-detect", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(IssueArtifact(workflow_id="adw-auto-detect", issue=issue))

        # Read without specifying model class
        restored = store.read_artifact("issue")

        assert isinstance(restored, IssueArtifact)
        assert restored.issue.id == 1

    def test_read_artifact_not_found(self, tmp_path):
        """Test read_artifact raises FileNotFoundError for missing artifact."""
        store = ArtifactStore("adw-missing", base_path=tmp_path)

        with pytest.raises(FileNotFoundError, match="Artifact not found: issue"):
            store.read_artifact("issue")

    def test_read_artifact_corrupted_json(self, tmp_path):
        """Test read_artifact raises ValueError for corrupted JSON."""
        store = ArtifactStore("adw-corrupted", base_path=tmp_path)
        artifact_path = tmp_path / "adw-corrupted" / "issue.json"
        artifact_path.write_text("{ invalid json }")

        # Pydantic may raise a validation error or JSON decode error depending on version
        with pytest.raises(ValueError):
            store.read_artifact("issue")

    def test_read_artifact_invalid_data(self, tmp_path):
        """Test read_artifact raises ValueError for invalid artifact data."""
        store = ArtifactStore("adw-invalid", base_path=tmp_path)
        artifact_path = tmp_path / "adw-invalid" / "issue.json"
        # Write valid JSON but missing required fields
        artifact_path.write_text('{"workflow_id": "test"}')

        with pytest.raises(ValueError, match="Failed to validate artifact"):
            store.read_artifact("issue")

    def test_artifact_exists_true(self, tmp_path):
        """Test artifact_exists returns True for existing artifact."""
        store = ArtifactStore("adw-exists", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(IssueArtifact(workflow_id="adw-exists", issue=issue))

        assert store.artifact_exists("issue") is True

    def test_artifact_exists_false(self, tmp_path):
        """Test artifact_exists returns False for missing artifact."""
        store = ArtifactStore("adw-no-exists", base_path=tmp_path)

        assert store.artifact_exists("issue") is False

    def test_list_artifacts_empty(self, tmp_path):
        """Test list_artifacts returns empty list for new workflow."""
        store = ArtifactStore("adw-empty", base_path=tmp_path)

        assert store.list_artifacts() == []

    def test_list_artifacts_with_artifacts(self, tmp_path):
        """Test list_artifacts returns all existing artifact types."""
        store = ArtifactStore("adw-multiple", base_path=tmp_path)

        # Write multiple artifacts
        issue = Issue(id=1, description="Test")
        store.write_artifact(IssueArtifact(workflow_id="adw-multiple", issue=issue))

        classify_data = ClassifyData(
            command="/adw-feature-plan",
            classification={"type": "feature", "level": "low"},
        )
        store.write_artifact(
            ClassificationArtifact(workflow_id="adw-multiple", classify_data=classify_data)
        )

        artifacts = store.list_artifacts()

        assert "issue" in artifacts
        assert "classification" in artifacts
        assert len(artifacts) == 2

    def test_get_artifact_info(self, tmp_path):
        """Test get_artifact_info returns file metadata."""
        store = ArtifactStore("adw-info", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(IssueArtifact(workflow_id="adw-info", issue=issue))

        info = store.get_artifact_info("issue")

        assert info is not None
        assert info["artifact_type"] == "issue"
        assert "file_path" in info
        assert info["size_bytes"] > 0
        assert isinstance(info["modified_at"], datetime)

    def test_get_artifact_info_not_found(self, tmp_path):
        """Test get_artifact_info returns None for missing artifact."""
        store = ArtifactStore("adw-no-info", base_path=tmp_path)

        info = store.get_artifact_info("issue")

        assert info is None

    def test_delete_artifact(self, tmp_path):
        """Test delete_artifact removes artifact file."""
        store = ArtifactStore("adw-delete", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(IssueArtifact(workflow_id="adw-delete", issue=issue))

        assert store.artifact_exists("issue") is True

        result = store.delete_artifact("issue")

        assert result is True
        assert store.artifact_exists("issue") is False

    def test_delete_artifact_not_found(self, tmp_path):
        """Test delete_artifact returns False for missing artifact."""
        store = ArtifactStore("adw-no-delete", base_path=tmp_path)

        result = store.delete_artifact("issue")

        assert result is False

    def test_multiple_artifact_types(self, tmp_path):
        """Test storing and retrieving multiple artifact types."""
        store = ArtifactStore("adw-multi-type", base_path=tmp_path)

        # Create and store various artifacts
        issue = Issue(id=1, description="Multi-type test")
        store.write_artifact(IssueArtifact(workflow_id="adw-multi-type", issue=issue))

        classify_data = ClassifyData(
            command="/adw-chore-plan",
            classification={"type": "chore", "level": "small"},
        )
        store.write_artifact(
            ClassificationArtifact(workflow_id="adw-multi-type", classify_data=classify_data)
        )

        plan_data = PlanData(plan="Plan output", summary="Summary")
        store.write_artifact(PlanArtifact(workflow_id="adw-multi-type", plan_data=plan_data))

        # Verify all artifacts can be read back
        issue_artifact = store.read_artifact("issue")
        classification_artifact = store.read_artifact("classification")
        plan_artifact = store.read_artifact("plan")

        assert issue_artifact.issue.id == 1
        assert classification_artifact.classify_data.command == "/adw-chore-plan"
        assert plan_artifact.plan_data.plan == "Plan output"

    def test_store_overwrites_existing_artifact(self, tmp_path):
        """Test writing an artifact overwrites existing one."""
        store = ArtifactStore("adw-overwrite", base_path=tmp_path)

        # Write initial artifact
        issue1 = Issue(id=1, description="First version")
        store.write_artifact(IssueArtifact(workflow_id="adw-overwrite", issue=issue1))

        # Overwrite with new artifact
        issue2 = Issue(id=2, description="Second version")
        store.write_artifact(IssueArtifact(workflow_id="adw-overwrite", issue=issue2))

        # Read back should get second version
        artifact = store.read_artifact("issue")
        assert artifact.issue.id == 2
        assert artifact.issue.description == "Second version"


class TestArtifactStoreIntegration:
    """Integration tests for complete artifact workflows."""

    def test_full_workflow_artifact_chain(self, tmp_path):
        """Test a complete workflow storing all artifact types."""
        store = ArtifactStore("adw-full-chain", base_path=tmp_path)
        workflow_id = "adw-full-chain"

        # 1. Issue artifact
        issue = Issue(id=100, description="Full workflow test")
        store.write_artifact(IssueArtifact(workflow_id=workflow_id, issue=issue))

        # 2. Classification artifact
        classify_data = ClassifyData(
            command="/adw-feature-plan",
            classification={"type": "feature", "level": "medium"},
        )
        store.write_artifact(
            ClassificationArtifact(workflow_id=workflow_id, classify_data=classify_data)
        )

        # 3. Plan artifact
        plan_data = PlanData(
            plan="# Feature Plan\n...", summary="Feature summary", session_id="sess-123"
        )
        store.write_artifact(PlanArtifact(workflow_id=workflow_id, plan_data=plan_data))

        # 4. Implementation artifact
        implement_data = ImplementData(output="Implementation complete")
        store.write_artifact(
            ImplementationArtifact(workflow_id=workflow_id, implement_data=implement_data)
        )

        # 5. Review artifact
        review_data = ReviewData(review_text="Code looks good")
        store.write_artifact(ReviewArtifact(workflow_id=workflow_id, review_data=review_data))

        # 7. Review addressed artifact
        store.write_artifact(ReviewAddressedArtifact(workflow_id=workflow_id, success=True))

        # 8. Quality check artifact
        store.write_artifact(
            QualityCheckArtifact(
                workflow_id=workflow_id, output="All checks passed", tools=["ruff", "mypy"]
            )
        )

        # 9. Acceptance artifact
        store.write_artifact(AcceptanceArtifact(workflow_id=workflow_id, success=True))

        # 10. PR metadata artifact
        store.write_artifact(
            PRMetadataArtifact(
                workflow_id=workflow_id,
                title="feat: Add new feature",
                summary="This PR implements...",
                commits=[],
            )
        )

        # 11. Pull request artifact
        store.write_artifact(
            PullRequestArtifact(
                workflow_id=workflow_id,
                url="https://github.com/org/repo/pull/1",
                platform="github",
            )
        )

        # Verify all 10 artifacts exist
        artifacts = store.list_artifacts()
        assert len(artifacts) == 10

        # Verify each type is present
        expected_types = [
            "issue",
            "classification",
            "plan",
            "implementation",
            "review",
            "review_addressed",
            "quality_check",
            "acceptance",
            "pr_metadata",
            "pull_request",
        ]
        for artifact_type in expected_types:
            assert artifact_type in artifacts
