"""Unit tests for workflow artifact persistence layer."""

import json
from datetime import datetime
from unittest.mock import patch

import pytest

from rouge.core.models import Issue
from rouge.core.workflow.artifacts import (
    ARTIFACT_MODELS,
    ArtifactStore,
    CodeQualityArtifact,
    ComposeRequestArtifact,
    FetchIssueArtifact,
    GhPullRequestArtifact,
    GlabPullRequestArtifact,
    ImplementArtifact,
    ImplementDirectArtifact,
    PlanArtifact,
    PullRequestEntry,
)
from rouge.core.workflow.types import (
    ImplementData,
    PlanData,
    RepoChangeDetail,
)


class TestArtifactModels:
    """Tests for artifact model definitions."""

    def test_issue_artifact_creation(self) -> None:
        """Test FetchIssueArtifact can be created with valid data."""
        issue = Issue(id=1, description="Test issue")
        artifact = FetchIssueArtifact(
            workflow_id="adw-123",
            issue=issue,
        )

        assert artifact.workflow_id == "adw-123"
        assert artifact.artifact_type == "fetch-issue"
        assert artifact.issue.id == 1
        assert artifact.issue.description == "Test issue"
        assert isinstance(artifact.created_at, datetime)

    def test_plan_artifact_creation(self) -> None:
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

    def test_implementation_artifact_creation(self) -> None:
        """Test ImplementArtifact can be created with valid data."""
        implement_data = ImplementData(output="Implementation output")
        artifact = ImplementArtifact(
            workflow_id="adw-123",
            implement_data=implement_data,
        )

        assert artifact.artifact_type == "implement"
        assert artifact.implement_data.output == "Implementation output"

    def test_direct_implementation_artifact_creation(self) -> None:
        """Test ImplementDirectArtifact can be created with valid data."""
        implement_data = ImplementData(output="Direct implementation output")
        artifact = ImplementDirectArtifact(
            workflow_id="adw-123",
            implement_data=implement_data,
        )

        assert artifact.artifact_type == "implement:direct"
        assert artifact.implement_data.output == "Direct implementation output"

    def test_implement_data_empty_affected_repos_backward_compat(self) -> None:
        """ImplementData without affected_repos defaults to empty list (backward compat)."""
        data = ImplementData(output="Some output")

        assert data.affected_repos == []

    def test_implement_data_with_populated_affected_repos(self) -> None:
        """ImplementData accepts a populated affected_repos list."""
        detail = RepoChangeDetail(
            repo_path="/path/to/repo",
            files_modified=["src/foo.py", "tests/test_foo.py"],
            git_diff_stat="2 files changed, 10 insertions(+), 3 deletions(-)",
        )
        data = ImplementData(output="Done", affected_repos=[detail])

        assert len(data.affected_repos) == 1
        assert data.affected_repos[0].repo_path == "/path/to/repo"
        assert data.affected_repos[0].files_modified == ["src/foo.py", "tests/test_foo.py"]
        assert "2 files changed" in data.affected_repos[0].git_diff_stat

    def test_repo_change_detail_field_defaults(self) -> None:
        """RepoChangeDetail has sensible defaults for optional fields."""
        detail = RepoChangeDetail(repo_path="/repo")

        assert detail.repo_path == "/repo"
        assert detail.files_modified == []
        assert detail.git_diff_stat == ""

    def test_quality_check_artifact_creation(self) -> None:
        """Test CodeQualityArtifact can be created with valid data."""
        repos = [{"repo": "/srv/app", "issues": [], "tools": ["ruff", "mypy"]}]
        artifact = CodeQualityArtifact(
            workflow_id="adw-123",
            output="code-quality",
            repos=repos,
            parsed_data={"repos": repos},
        )

        assert artifact.artifact_type == "code-quality"
        assert artifact.output == "code-quality"
        assert len(artifact.repos) == 1
        assert artifact.repos[0].repo == "/srv/app"
        assert artifact.repos[0].tools == ["ruff", "mypy"]
        assert artifact.parsed_data == {"repos": repos}

    def test_pr_metadata_artifact_creation(self) -> None:
        """Test ComposeRequestArtifact can be created with valid data."""
        repos = [
            {
                "repo": "/srv/app",
                "title": "Add new feature",
                "summary": "This PR adds a new feature",
                "commits": [{"sha": "abc123", "message": "feat: add feature"}],
            }
        ]
        artifact = ComposeRequestArtifact(
            workflow_id="adw-123",
            repos=repos,
        )

        assert artifact.artifact_type == "compose-request"
        assert len(artifact.repos) == 1
        assert artifact.repos[0].title == "Add new feature"
        assert artifact.repos[0].commits[0].sha == "abc123"

    def test_pull_request_artifact_creation(self) -> None:
        """Test GhPullRequestArtifact can be created with valid data."""
        entry = PullRequestEntry(
            repo="org/repo",
            repo_path="/path/to/repo",
            url="https://github.com/org/repo/pull/42",
            number=42,
        )
        artifact = GhPullRequestArtifact(
            workflow_id="adw-123",
            pull_requests=[entry],
            platform="github",
        )

        assert artifact.artifact_type == "gh-pull-request"
        assert len(artifact.pull_requests) == 1
        assert artifact.pull_requests[0].url == "https://github.com/org/repo/pull/42"
        assert artifact.pull_requests[0].number == 42
        assert artifact.pull_requests[0].adopted is False
        assert artifact.platform == "github"

    def test_gh_pull_request_artifact_empty_pull_requests(self) -> None:
        """Test GhPullRequestArtifact can be created with zero pull requests."""
        artifact = GhPullRequestArtifact(
            workflow_id="adw-123",
            pull_requests=[],
        )

        assert artifact.artifact_type == "gh-pull-request"
        assert artifact.pull_requests == []
        assert artifact.platform == "github"

    def test_gh_pull_request_artifact_two_entries(self) -> None:
        """Test GhPullRequestArtifact with two PullRequestEntry items."""
        entries = [
            PullRequestEntry(
                repo="org/repo-a",
                repo_path="/path/to/a",
                url="https://github.com/org/repo-a/pull/1",
                number=1,
            ),
            PullRequestEntry(
                repo="org/repo-b",
                repo_path="/path/to/b",
                url="https://github.com/org/repo-b/pull/2",
                number=2,
                adopted=True,
            ),
        ]
        artifact = GhPullRequestArtifact(
            workflow_id="adw-123",
            pull_requests=entries,
        )

        assert len(artifact.pull_requests) == 2
        assert artifact.pull_requests[0].repo == "org/repo-a"
        assert artifact.pull_requests[1].adopted is True

    def test_glab_pull_request_artifact_creation(self) -> None:
        """Test GlabPullRequestArtifact can be created with valid data."""
        entry = PullRequestEntry(
            repo="org/repo",
            repo_path="/path/to/repo",
            url="https://gitlab.com/org/repo/-/merge_requests/10",
            number=10,
        )
        artifact = GlabPullRequestArtifact(
            workflow_id="adw-456",
            pull_requests=[entry],
        )

        assert artifact.artifact_type == "glab-pull-request"
        assert len(artifact.pull_requests) == 1
        assert artifact.pull_requests[0].url == "https://gitlab.com/org/repo/-/merge_requests/10"
        assert artifact.platform == "gitlab"

    def test_glab_pull_request_artifact_empty(self) -> None:
        """Test GlabPullRequestArtifact can be created with zero pull requests."""
        artifact = GlabPullRequestArtifact(
            workflow_id="adw-456",
            pull_requests=[],
        )

        assert artifact.artifact_type == "glab-pull-request"
        assert artifact.pull_requests == []

    def test_glab_pull_request_artifact_two_entries(self) -> None:
        """Test GlabPullRequestArtifact with two PullRequestEntry items."""
        entries = [
            PullRequestEntry(
                repo="group/project-a",
                repo_path="/path/to/a",
                url="https://gitlab.com/group/project-a/-/merge_requests/5",
                number=5,
            ),
            PullRequestEntry(
                repo="group/project-b",
                repo_path="/path/to/b",
                url="https://gitlab.com/group/project-b/-/merge_requests/6",
                number=6,
            ),
        ]
        artifact = GlabPullRequestArtifact(
            workflow_id="adw-456",
            pull_requests=entries,
        )

        assert len(artifact.pull_requests) == 2

    def test_pull_request_entry_adopted_defaults_false(self) -> None:
        """Test PullRequestEntry.adopted defaults to False."""
        entry = PullRequestEntry(
            repo="org/repo",
            repo_path="/path/to/repo",
            url="https://github.com/org/repo/pull/1",
        )

        assert entry.adopted is False
        assert entry.number is None

    def test_artifact_models_mapping_complete(self) -> None:
        """Test ARTIFACT_MODELS contains all expected types."""
        expected_types = {
            "fetch-issue",
            "plan",
            "implement",
            "implement:direct",
            "code-quality",
            "compose-request",
            "gh-pull-request",
            "fetch-patch",
            "git-branch",
            "git-checkout",
            "compose-commits",
            "glab-pull-request",
            "workflow-state",
        }

        assert set(ARTIFACT_MODELS.keys()) == expected_types


class TestArtifactSerialization:
    """Tests for artifact JSON serialization/deserialization."""

    def test_issue_artifact_round_trip(self) -> None:
        """Test FetchIssueArtifact can be serialized and deserialized."""
        issue = Issue(id=42, description="Test issue for round trip")
        artifact = FetchIssueArtifact(
            workflow_id="adw-test",
            issue=issue,
        )

        json_str = artifact.model_dump_json()
        restored = FetchIssueArtifact.model_validate_json(json_str)

        assert restored.workflow_id == artifact.workflow_id
        assert restored.artifact_type == "fetch-issue"
        assert restored.issue.id == 42
        assert restored.issue.description == "Test issue for round trip"

    def test_gh_pull_request_artifact_round_trip_empty(self) -> None:
        """Test GhPullRequestArtifact serializes/deserializes with zero entries."""
        artifact = GhPullRequestArtifact(
            workflow_id="adw-rt",
            pull_requests=[],
        )

        json_str = artifact.model_dump_json()
        restored = GhPullRequestArtifact.model_validate_json(json_str)

        assert restored.artifact_type == "gh-pull-request"
        assert restored.pull_requests == []
        assert restored.platform == "github"

    def test_gh_pull_request_artifact_round_trip_one_entry(self) -> None:
        """Test GhPullRequestArtifact serializes/deserializes with one entry."""
        entry = PullRequestEntry(
            repo="org/repo",
            repo_path="/path/to/repo",
            url="https://github.com/org/repo/pull/7",
            number=7,
        )
        artifact = GhPullRequestArtifact(
            workflow_id="adw-rt",
            pull_requests=[entry],
        )

        json_str = artifact.model_dump_json()
        restored = GhPullRequestArtifact.model_validate_json(json_str)

        assert len(restored.pull_requests) == 1
        assert restored.pull_requests[0].url == "https://github.com/org/repo/pull/7"
        assert restored.pull_requests[0].number == 7
        assert restored.pull_requests[0].adopted is False

    def test_gh_pull_request_artifact_round_trip_two_entries(self) -> None:
        """Test GhPullRequestArtifact serializes/deserializes with two entries."""
        entries = [
            PullRequestEntry(
                repo="org/a",
                repo_path="/a",
                url="https://github.com/org/a/pull/1",
                number=1,
            ),
            PullRequestEntry(
                repo="org/b",
                repo_path="/b",
                url="https://github.com/org/b/pull/2",
                number=2,
                adopted=True,
            ),
        ]
        artifact = GhPullRequestArtifact(
            workflow_id="adw-rt",
            pull_requests=entries,
        )

        json_str = artifact.model_dump_json()
        restored = GhPullRequestArtifact.model_validate_json(json_str)

        assert len(restored.pull_requests) == 2
        assert restored.pull_requests[1].adopted is True

    def test_glab_pull_request_artifact_round_trip_empty(self) -> None:
        """Test GlabPullRequestArtifact serializes/deserializes with zero entries."""
        artifact = GlabPullRequestArtifact(
            workflow_id="adw-rt",
            pull_requests=[],
        )

        json_str = artifact.model_dump_json()
        restored = GlabPullRequestArtifact.model_validate_json(json_str)

        assert restored.artifact_type == "glab-pull-request"
        assert restored.pull_requests == []
        assert restored.platform == "gitlab"

    def test_glab_pull_request_artifact_round_trip_one_entry(self) -> None:
        """Test GlabPullRequestArtifact serializes/deserializes with one entry."""
        entry = PullRequestEntry(
            repo="group/project",
            repo_path="/path/to/project",
            url="https://gitlab.com/group/project/-/merge_requests/3",
            number=3,
        )
        artifact = GlabPullRequestArtifact(
            workflow_id="adw-rt",
            pull_requests=[entry],
        )

        json_str = artifact.model_dump_json()
        restored = GlabPullRequestArtifact.model_validate_json(json_str)

        assert len(restored.pull_requests) == 1
        assert restored.pull_requests[0].number == 3
        assert restored.pull_requests[0].adopted is False

    def test_glab_pull_request_artifact_round_trip_two_entries(self) -> None:
        """Test GlabPullRequestArtifact serializes/deserializes with two entries."""
        entries = [
            PullRequestEntry(
                repo="g/p1",
                repo_path="/p1",
                url="https://gitlab.com/g/p1/-/merge_requests/10",
                number=10,
            ),
            PullRequestEntry(
                repo="g/p2",
                repo_path="/p2",
                url="https://gitlab.com/g/p2/-/merge_requests/11",
                number=11,
                adopted=True,
            ),
        ]
        artifact = GlabPullRequestArtifact(
            workflow_id="adw-rt",
            pull_requests=entries,
        )

        json_str = artifact.model_dump_json()
        restored = GlabPullRequestArtifact.model_validate_json(json_str)

        assert len(restored.pull_requests) == 2
        assert restored.pull_requests[1].adopted is True

    def test_implement_artifact_round_trip_with_affected_repos(self) -> None:
        """ImplementArtifact with affected_repos survives JSON round-trip."""
        details = [
            RepoChangeDetail(
                repo_path="/path/a",
                files_modified=["a.py"],
                git_diff_stat="1 file changed",
            ),
            RepoChangeDetail(repo_path="/path/b"),
        ]
        data = ImplementData(output="done", session_id="s1", affected_repos=details)
        artifact = ImplementArtifact(workflow_id="adw-rt", implement_data=data)

        json_str = artifact.model_dump_json()
        restored = ImplementArtifact.model_validate_json(json_str)

        assert restored.artifact_type == "implement"
        assert restored.implement_data.output == "done"
        assert restored.implement_data.session_id == "s1"
        assert len(restored.implement_data.affected_repos) == 2
        assert restored.implement_data.affected_repos[0].repo_path == "/path/a"
        assert restored.implement_data.affected_repos[0].files_modified == ["a.py"]
        assert restored.implement_data.affected_repos[1].repo_path == "/path/b"
        assert restored.implement_data.affected_repos[1].files_modified == []

    def test_implement_artifact_round_trip_empty_affected_repos(self) -> None:
        """ImplementArtifact with no affected_repos survives JSON round-trip."""
        data = ImplementData(output="legacy output")
        artifact = ImplementArtifact(workflow_id="adw-rt", implement_data=data)

        json_str = artifact.model_dump_json()
        restored = ImplementArtifact.model_validate_json(json_str)

        assert restored.implement_data.affected_repos == []

    def test_artifact_json_is_valid(self) -> None:
        """Test artifact JSON is valid and human-readable."""
        issue = Issue(id=1, description="Test")
        artifact = FetchIssueArtifact(workflow_id="adw-123", issue=issue)

        json_str = artifact.model_dump_json(indent=2)
        parsed = json.loads(json_str)

        assert "workflow_id" in parsed
        assert "artifact_type" in parsed
        assert "issue" in parsed
        assert parsed["artifact_type"] == "fetch-issue"


class TestArtifactStore:
    """Tests for ArtifactStore filesystem operations."""

    def test_store_initialization_creates_directory(self, tmp_path) -> None:
        """Test ArtifactStore creates workflow directory on init."""
        store = ArtifactStore("adw-test-123", base_path=tmp_path)

        assert store.workflow_id == "adw-test-123"
        assert store.workflow_dir == tmp_path / "adw-test-123"
        assert store.workflow_dir.exists()
        assert store.workflow_dir.is_dir()

    def test_store_initialization_with_rouge_paths(self, tmp_path) -> None:
        """Test ArtifactStore uses RougePaths.get_workflows_dir() by default."""
        with patch("rouge.core.paths.get_working_dir", return_value=str(tmp_path)):
            store = ArtifactStore("adw-default-123")

            assert store.workflow_dir == tmp_path / ".rouge" / "workflows" / "adw-default-123"
            assert store.workflow_dir.exists()

    def test_write_artifact(self, tmp_path) -> None:
        """Test writing an artifact to disk."""
        store = ArtifactStore("adw-write-test", base_path=tmp_path)
        issue = Issue(id=1, description="Test issue")
        artifact = FetchIssueArtifact(workflow_id="adw-write-test", issue=issue)

        store.write_artifact(artifact)

        artifact_path = tmp_path / "adw-write-test" / "fetch-issue.json"
        assert artifact_path.exists()

        # Verify content
        content = json.loads(artifact_path.read_text())
        assert content["artifact_type"] == "fetch-issue"
        assert content["issue"]["id"] == 1

    def test_read_artifact(self, tmp_path) -> None:
        """Test reading an artifact from disk."""
        store = ArtifactStore("adw-read-test", base_path=tmp_path)
        issue = Issue(id=42, description="Read test issue")
        original = FetchIssueArtifact(workflow_id="adw-read-test", issue=issue)

        store.write_artifact(original)
        restored = store.read_artifact("fetch-issue", FetchIssueArtifact)

        assert restored.workflow_id == "adw-read-test"
        assert restored.issue.id == 42
        assert restored.issue.description == "Read test issue"

    def test_read_artifact_auto_detects_model(self, tmp_path) -> None:
        """Test read_artifact auto-detects model class from artifact type."""
        store = ArtifactStore("adw-auto-detect", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-auto-detect", issue=issue))

        # Read without specifying model class
        restored = store.read_artifact("fetch-issue")

        assert isinstance(restored, FetchIssueArtifact)
        assert restored.issue.id == 1

    def test_read_artifact_not_found(self, tmp_path) -> None:
        """Test read_artifact raises FileNotFoundError for missing artifact."""
        store = ArtifactStore("adw-missing", base_path=tmp_path)

        with pytest.raises(FileNotFoundError, match="Artifact not found: fetch-issue"):
            store.read_artifact("fetch-issue")

    def test_read_artifact_corrupted_json(self, tmp_path) -> None:
        """Test read_artifact raises ValueError for corrupted JSON."""
        store = ArtifactStore("adw-corrupted", base_path=tmp_path)
        artifact_path = tmp_path / "adw-corrupted" / "fetch-issue.json"
        artifact_path.write_text("{ invalid json }")

        # Pydantic may raise a validation error or JSON decode error depending on version
        with pytest.raises(ValueError):
            store.read_artifact("fetch-issue")

    def test_read_artifact_invalid_data(self, tmp_path) -> None:
        """Test read_artifact raises ValueError for invalid artifact data."""
        store = ArtifactStore("adw-invalid", base_path=tmp_path)
        artifact_path = tmp_path / "adw-invalid" / "fetch-issue.json"
        # Write valid JSON but missing required fields
        artifact_path.write_text('{"workflow_id": "test"}')

        with pytest.raises(ValueError, match="Failed to validate artifact"):
            store.read_artifact("fetch-issue")

    def test_artifact_exists_true(self, tmp_path) -> None:
        """Test artifact_exists returns True for existing artifact."""
        store = ArtifactStore("adw-exists", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-exists", issue=issue))

        assert store.artifact_exists("fetch-issue") is True

    def test_artifact_exists_false(self, tmp_path) -> None:
        """Test artifact_exists returns False for missing artifact."""
        store = ArtifactStore("adw-no-exists", base_path=tmp_path)

        assert store.artifact_exists("fetch-issue") is False

    def test_list_artifacts_empty(self, tmp_path) -> None:
        """Test list_artifacts returns empty list for new workflow."""
        store = ArtifactStore("adw-empty", base_path=tmp_path)

        assert store.list_artifacts() == []

    def test_list_artifacts_with_artifacts(self, tmp_path) -> None:
        """Test list_artifacts returns all existing artifact types."""
        store = ArtifactStore("adw-multiple", base_path=tmp_path)

        # Write multiple artifacts
        issue = Issue(id=1, description="Test")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-multiple", issue=issue))

        plan_data = PlanData(plan="Test plan", summary="Test summary")
        store.write_artifact(PlanArtifact(workflow_id="adw-multiple", plan_data=plan_data))

        artifacts = store.list_artifacts()

        assert "fetch-issue" in artifacts
        assert "plan" in artifacts
        assert len(artifacts) == 2

    def test_get_artifact_info(self, tmp_path) -> None:
        """Test get_artifact_info returns file metadata."""
        store = ArtifactStore("adw-info", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-info", issue=issue))

        info = store.get_artifact_info("fetch-issue")

        assert info is not None
        assert info["artifact_type"] == "fetch-issue"
        assert "file_path" in info
        assert info["size_bytes"] > 0
        assert isinstance(info["modified_at"], datetime)

    def test_get_artifact_info_not_found(self, tmp_path) -> None:
        """Test get_artifact_info returns None for missing artifact."""
        store = ArtifactStore("adw-no-info", base_path=tmp_path)

        info = store.get_artifact_info("fetch-issue")

        assert info is None

    def test_delete_artifact(self, tmp_path) -> None:
        """Test delete_artifact removes artifact file."""
        store = ArtifactStore("adw-delete", base_path=tmp_path)
        issue = Issue(id=1, description="Test")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-delete", issue=issue))

        assert store.artifact_exists("fetch-issue") is True

        result = store.delete_artifact("fetch-issue")

        assert result is True
        assert store.artifact_exists("fetch-issue") is False

    def test_delete_artifact_not_found(self, tmp_path) -> None:
        """Test delete_artifact returns False for missing artifact."""
        store = ArtifactStore("adw-no-delete", base_path=tmp_path)

        result = store.delete_artifact("fetch-issue")

        assert result is False

    def test_multiple_artifact_types(self, tmp_path) -> None:
        """Test storing and retrieving multiple artifact types."""
        store = ArtifactStore("adw-multi-type", base_path=tmp_path)

        # Create and store various artifacts
        issue = Issue(id=1, description="Multi-type test")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-multi-type", issue=issue))

        plan_data = PlanData(plan="Plan output", summary="Summary")
        store.write_artifact(PlanArtifact(workflow_id="adw-multi-type", plan_data=plan_data))

        implement_data = ImplementData(output="Implementation output")
        store.write_artifact(
            ImplementArtifact(workflow_id="adw-multi-type", implement_data=implement_data)
        )

        # Verify all artifacts can be read back
        issue_artifact = store.read_artifact("fetch-issue")
        plan_artifact = store.read_artifact("plan")
        impl_artifact = store.read_artifact("implement")

        assert issue_artifact.issue.id == 1
        assert plan_artifact.plan_data.plan == "Plan output"
        assert impl_artifact.implement_data.output == "Implementation output"

    def test_store_overwrites_existing_artifact(self, tmp_path) -> None:
        """Test writing an artifact overwrites existing one."""
        store = ArtifactStore("adw-overwrite", base_path=tmp_path)

        # Write initial artifact
        issue1 = Issue(id=1, description="First version")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-overwrite", issue=issue1))

        # Overwrite with new artifact
        issue2 = Issue(id=2, description="Second version")
        store.write_artifact(FetchIssueArtifact(workflow_id="adw-overwrite", issue=issue2))

        # Read back should get second version
        artifact = store.read_artifact("fetch-issue")
        assert artifact.issue.id == 2
        assert artifact.issue.description == "Second version"


class TestArtifactStoreIntegration:
    """Integration tests for complete artifact workflows."""

    def test_full_workflow_artifact_chain(self, tmp_path) -> None:
        """Test a complete workflow storing all artifact types."""
        store = ArtifactStore("adw-full-chain", base_path=tmp_path)
        workflow_id = "adw-full-chain"

        # 1. Issue artifact
        issue = Issue(id=100, description="Full workflow test")
        store.write_artifact(FetchIssueArtifact(workflow_id=workflow_id, issue=issue))

        # 2. Plan artifact
        plan_data = PlanData(
            plan="# Feature Plan\n...", summary="Feature summary", session_id="sess-123"
        )
        store.write_artifact(PlanArtifact(workflow_id=workflow_id, plan_data=plan_data))

        # 3. Implementation artifact
        implement_data = ImplementData(output="Implementation complete")
        store.write_artifact(
            ImplementArtifact(workflow_id=workflow_id, implement_data=implement_data)
        )

        # 4. Quality check artifact
        store.write_artifact(
            CodeQualityArtifact(
                workflow_id=workflow_id, output="All checks passed", tools=["ruff", "mypy"]
            )
        )

        # 5. PR metadata artifact
        store.write_artifact(
            ComposeRequestArtifact(
                workflow_id=workflow_id,
                repos=[
                    {
                        "repo": "/srv/app",
                        "title": "feat: Add new feature",
                        "summary": "This PR implements...",
                        "commits": [],
                    }
                ],
            )
        )

        # 6. Pull request artifact
        store.write_artifact(
            GhPullRequestArtifact(
                workflow_id=workflow_id,
                pull_requests=[
                    PullRequestEntry(
                        repo="org/repo",
                        repo_path="/path/to/repo",
                        url="https://github.com/org/repo/pull/1",
                        number=1,
                    )
                ],
                platform="github",
            )
        )

        # Verify all 6 artifacts exist
        artifacts = store.list_artifacts()
        assert len(artifacts) == 6

        # Verify each type is present
        expected_types = [
            "fetch-issue",
            "plan",
            "implement",
            "code-quality",
            "compose-request",
            "gh-pull-request",
        ]
        for artifact_type in expected_types:
            assert artifact_type in artifacts
