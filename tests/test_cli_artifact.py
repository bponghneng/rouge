"""Tests for artifact CLI commands."""

from unittest.mock import patch

from typer.testing import CliRunner

from rouge.cli.cli import app
from rouge.core.models import Issue
from rouge.core.workflow.artifacts import ArtifactStore, FetchIssueArtifact

runner = CliRunner()

_WORKING_DIR_PATCH = "rouge.core.paths.get_working_dir"


class TestArtifactTypesCommand:
    """Tests for 'rouge artifact types' command."""

    def test_artifact_types_lists_all_types(self):
        """Test artifact types command lists all artifact types."""
        result = runner.invoke(app, ["artifact", "types"])
        assert result.exit_code == 0
        assert "Available artifact types" in result.output

        # Check for expected types
        assert "fetch-issue" in result.output
        assert "classify" in result.output
        assert "plan" in result.output
        assert "implement" in result.output

    def test_artifact_types_shows_count(self):
        """Test artifact types command shows total count."""
        result = runner.invoke(app, ["artifact", "types"])
        assert result.exit_code == 0
        assert "artifact type(s)" in result.output


class TestArtifactListCommand:
    """Tests for 'rouge artifact list' command."""

    def test_artifact_list_empty_workflow(self, tmp_path):
        """Test artifact list command for workflow with no artifacts."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            result = runner.invoke(app, ["artifact", "list", "adw-empty-test"])
            assert result.exit_code == 0
            assert "No artifacts found" in result.output

    def test_artifact_list_with_artifacts(self, tmp_path):
        """Test artifact list command for workflow with artifacts."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            # Create some test artifacts
            store = ArtifactStore("adw-test-list", base_path=tmp_path / ".rouge" / "workflows")
            issue = Issue(id=1, description="Test issue")
            store.write_artifact(FetchIssueArtifact(workflow_id="adw-test-list", issue=issue))

            result = runner.invoke(app, ["artifact", "list", "adw-test-list"])
            assert result.exit_code == 0
            assert "fetch-issue" in result.output
            assert "Total:" in result.output


class TestArtifactShowCommand:
    """Tests for 'rouge artifact show' command."""

    def test_artifact_show_invalid_type(self, tmp_path):
        """Test artifact show command with invalid artifact type."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            result = runner.invoke(app, ["artifact", "show", "adw-test", "invalid_type"])
            assert result.exit_code == 1
            assert "Invalid artifact type" in result.output

    def test_artifact_show_not_found(self, tmp_path):
        """Test artifact show command when artifact doesn't exist."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            # Create workflow directory but no artifact
            (tmp_path / ".rouge" / "workflows" / "adw-show-test").mkdir(parents=True, exist_ok=True)

            result = runner.invoke(app, ["artifact", "show", "adw-show-test", "fetch-issue"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_artifact_show_displays_content(self, tmp_path):
        """Test artifact show command displays artifact content."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            # Create test artifact
            store = ArtifactStore("adw-show-content", base_path=tmp_path / ".rouge" / "workflows")
            issue = Issue(id=42, description="Test issue for display")
            store.write_artifact(FetchIssueArtifact(workflow_id="adw-show-content", issue=issue))

            result = runner.invoke(app, ["artifact", "show", "adw-show-content", "fetch-issue"])
            assert result.exit_code == 0
            assert "42" in result.output  # Issue ID
            assert "Test issue for display" in result.output

    def test_artifact_show_raw_format(self, tmp_path):
        """Test artifact show command with --raw flag."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            # Create test artifact
            store = ArtifactStore("adw-show-raw", base_path=tmp_path / ".rouge" / "workflows")
            issue = Issue(id=1, description="Raw test")
            store.write_artifact(FetchIssueArtifact(workflow_id="adw-show-raw", issue=issue))

            result = runner.invoke(app, ["artifact", "show", "adw-show-raw", "fetch-issue", "--raw"])
            assert result.exit_code == 0
            # Raw output should not have headers
            assert "Artifact:" not in result.output


class TestArtifactDeleteCommand:
    """Tests for 'rouge artifact delete' command."""

    def test_artifact_delete_invalid_type(self, tmp_path):
        """Test artifact delete command with invalid artifact type."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            result = runner.invoke(app, ["artifact", "delete", "adw-test", "invalid_type"])
            assert result.exit_code == 1
            assert "Invalid artifact type" in result.output

    def test_artifact_delete_not_found(self, tmp_path):
        """Test artifact delete command when artifact doesn't exist."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            # Create workflow directory but no artifact
            (tmp_path / ".rouge" / "workflows" / "adw-delete-test").mkdir(
                parents=True, exist_ok=True
            )

            result = runner.invoke(app, ["artifact", "delete", "adw-delete-test", "fetch-issue"])
            assert result.exit_code == 1
            assert "not found" in result.output

    def test_artifact_delete_with_force(self, tmp_path):
        """Test artifact delete command with --force flag."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            # Create test artifact
            store = ArtifactStore("adw-delete-force", base_path=tmp_path / ".rouge" / "workflows")
            issue = Issue(id=1, description="Delete test")
            store.write_artifact(FetchIssueArtifact(workflow_id="adw-delete-force", issue=issue))

            assert store.artifact_exists("fetch-issue")

            result = runner.invoke(
                app, ["artifact", "delete", "adw-delete-force", "fetch-issue", "--force"]
            )
            assert result.exit_code == 0
            assert "Deleted" in result.output

            # Verify artifact is gone
            assert not store.artifact_exists("fetch-issue")


class TestArtifactPathCommand:
    """Tests for 'rouge artifact path' command."""

    def test_artifact_path_shows_directory(self, tmp_path):
        """Test artifact path command shows workflow directory."""
        with patch(_WORKING_DIR_PATCH, return_value=str(tmp_path)):
            result = runner.invoke(app, ["artifact", "path", "adw-path-test"])
            assert result.exit_code == 0
            assert "adw-path-test" in result.output
