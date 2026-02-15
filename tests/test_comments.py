"""Unit tests for comment notification utilities."""

from unittest.mock import patch

from rouge.core.models import Comment, Issue
from rouge.core.notifications.comments import (
    emit_artifact_comment,
    emit_comment_from_payload,
)
from rouge.core.workflow.artifacts import (
    AcceptanceArtifact,
    ClassifyArtifact,
    CodeQualityArtifact,
    CodeReviewArtifact,
    ComposeCommitsArtifact,
    ComposeRequestArtifact,
    FetchIssueArtifact,
    FetchPatchArtifact,
    GhPullRequestArtifact,
    GitSetupArtifact,
    GlabPullRequestArtifact,
    ImplementArtifact,
    PlanArtifact,
    ReviewFixArtifact,
)
from rouge.core.workflow.types import (
    ClassifyData,
    ImplementData,
    PlanData,
    ReviewData,
)


class TestEmitArtifactComment:
    """Tests for emit_artifact_comment helper function."""

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_artifact_comment_with_valid_issue_id(self, mock_create_comment):
        """Test emit_artifact_comment with valid artifact and issue_id."""
        # Create a test artifact
        plan_data = PlanData(plan="# Test Plan\n...", summary="Test summary")
        artifact = PlanArtifact(workflow_id="adw-test-123", plan_data=plan_data)

        # Mock the database create_comment function
        mock_comment = Comment(
            id=42,
            issue_id=1,
            comment="Artifact saved: plan",
            raw={
                "artifact_type": "plan",
                "artifact": artifact.model_dump(mode="json"),
            },
            source="artifact",
            type="plan",
            adw_id="adw-test-123",
        )
        mock_create_comment.return_value = mock_comment

        # Call the helper
        status, message = emit_artifact_comment(
            issue_id=1, adw_id="adw-test-123", artifact=artifact
        )

        # Verify success
        assert status == "success"
        assert "Comment inserted" in message
        assert "ID=42" in message

        # Verify create_comment was called
        mock_create_comment.assert_called_once()
        call_args = mock_create_comment.call_args[0][0]
        assert isinstance(call_args, Comment)
        assert call_args.issue_id == 1
        assert call_args.comment == "Artifact saved: plan"
        assert call_args.source == "artifact"
        assert call_args.type == "plan"
        assert call_args.adw_id == "adw-test-123"

    def test_emit_artifact_comment_payload_construction(self):
        """Test that emit_artifact_comment constructs correct payload."""
        # Create a test artifact
        classify_data = ClassifyData(
            command="/adw-feature-plan",
            classification={"type": "feature", "level": "medium"},
        )
        artifact = ClassifyArtifact(workflow_id="adw-classify-test", classify_data=classify_data)

        # Mock create_comment to capture the payload
        with patch("rouge.core.notifications.comments.create_comment") as mock_create:
            mock_create.return_value = Comment(
                id=1,
                issue_id=5,
                comment="test",
                adw_id="adw-classify-test",
            )

            emit_artifact_comment(issue_id=5, adw_id="adw-classify-test", artifact=artifact)

            # Verify the comment payload
            call_args = mock_create.call_args[0][0]
            assert call_args.comment == "Artifact saved: classify"
            assert call_args.source == "artifact"
            assert call_args.type == "classify"
            assert call_args.raw["artifact_type"] == "classify"
            assert "artifact" in call_args.raw
            assert call_args.raw["artifact"]["workflow_id"] == "adw-classify-test"

    def test_emit_artifact_comment_with_none_issue_id(self):
        """Test emit_artifact_comment with issue_id=None (verify skipped status)."""
        # Create a test artifact
        implement_data = ImplementData(output="Implementation complete")
        artifact = ImplementArtifact(workflow_id="adw-no-issue", implement_data=implement_data)

        # Call the helper with issue_id=None
        status, message = emit_artifact_comment(
            issue_id=None, adw_id="adw-no-issue", artifact=artifact
        )

        # Verify skipped status
        assert status == "skipped"
        assert "No issue_id" in message
        assert "logged to console" in message

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_artifact_comment_raw_field_contains_full_artifact(self, mock_create_comment):
        """Test that raw field contains the full serialized artifact JSON."""
        # Create artifact with nested data
        review_data = ReviewData(review_text="Code review feedback")
        artifact = CodeReviewArtifact(workflow_id="adw-review-test", review_data=review_data)

        mock_create_comment.return_value = Comment(
            id=1, issue_id=10, comment="test", adw_id="adw-review-test"
        )

        emit_artifact_comment(issue_id=10, adw_id="adw-review-test", artifact=artifact)

        # Get the comment that was passed to create_comment
        call_args = mock_create_comment.call_args[0][0]

        # Verify raw field structure
        assert "artifact_type" in call_args.raw
        assert "artifact" in call_args.raw
        assert call_args.raw["artifact_type"] == "code-review"

        # Verify the artifact field contains the full serialized artifact
        artifact_json = call_args.raw["artifact"]
        assert artifact_json["workflow_id"] == "adw-review-test"
        assert artifact_json["artifact_type"] == "code-review"
        assert "review_data" in artifact_json
        assert artifact_json["review_data"]["review_text"] == "Code review feedback"
        assert "created_at" in artifact_json

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_artifact_comment_type_compatibility_all_artifact_types(self, mock_create_comment):
        """Test emit_artifact_comment with all ArtifactType values to verify type compatibility."""
        mock_create_comment.return_value = Comment(
            id=1, issue_id=100, comment="test", adw_id="adw-type-test"
        )

        # Test each artifact type
        test_cases = [
            # (artifact_instance, expected_type)
            (
                FetchIssueArtifact(
                    workflow_id="adw-type-test",
                    issue=Issue(id=1, description="Test issue"),
                ),
                "fetch-issue",
            ),
            (
                ClassifyArtifact(
                    workflow_id="adw-type-test",
                    classify_data=ClassifyData(
                        command="/adw-feature-plan", classification={"type": "feature"}
                    ),
                ),
                "classify",
            ),
            (
                PlanArtifact(
                    workflow_id="adw-type-test",
                    plan_data=PlanData(plan="Plan text", summary="Summary"),
                ),
                "plan",
            ),
            (
                ImplementArtifact(
                    workflow_id="adw-type-test",
                    implement_data=ImplementData(output="Output"),
                ),
                "implement",
            ),
            (
                CodeReviewArtifact(
                    workflow_id="adw-type-test",
                    review_data=ReviewData(review_text="Review"),
                ),
                "code-review",
            ),
            (
                ReviewFixArtifact(workflow_id="adw-type-test", success=True),
                "review-fix",
            ),
            (
                CodeQualityArtifact(
                    workflow_id="adw-type-test",
                    output="Quality output",
                    tools=["ruff"],
                ),
                "code-quality",
            ),
            (
                AcceptanceArtifact(workflow_id="adw-type-test", success=True),
                "acceptance",
            ),
            (
                ComposeRequestArtifact(
                    workflow_id="adw-type-test",
                    title="PR Title",
                    summary="PR Summary",
                ),
                "compose-request",
            ),
            (
                GhPullRequestArtifact(
                    workflow_id="adw-type-test",
                    url="https://github.com/org/repo/pull/1",
                ),
                "gh-pull-request",
            ),
            (
                FetchPatchArtifact(
                    workflow_id="adw-type-test",
                    patch=Issue(id=2, description="Patch issue", type="patch"),
                ),
                "fetch-patch",
            ),
            (
                GitSetupArtifact(workflow_id="adw-type-test", branch="feature-branch"),
                "git-setup",
            ),
            (
                ComposeCommitsArtifact(
                    workflow_id="adw-type-test",
                    summary="Commits summary",
                    commits=[],
                ),
                "compose-commits",
            ),
            (
                GlabPullRequestArtifact(
                    workflow_id="adw-type-test",
                    url="https://gitlab.com/org/repo/-/merge_requests/1",
                ),
                "glab-pull-request",
            ),
        ]

        for artifact, expected_type in test_cases:
            mock_create_comment.reset_mock()

            status, message = emit_artifact_comment(
                issue_id=100, adw_id="adw-type-test", artifact=artifact
            )

            # Verify success
            assert status == "success", f"Failed for artifact type {expected_type}"

            # Verify the comment type matches the artifact type
            call_args = mock_create_comment.call_args[0][0]
            assert (
                call_args.type == expected_type
            ), f"Type mismatch for {expected_type}: got {call_args.type}"
            assert call_args.source == "artifact"
            assert f"Artifact saved: {expected_type}" == call_args.comment

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_artifact_comment_database_error_handling(self, mock_create_comment):
        """Test emit_artifact_comment handles database errors gracefully."""
        # Create a test artifact
        artifact = AcceptanceArtifact(workflow_id="adw-error-test", success=True)

        # Mock create_comment to raise an exception
        mock_create_comment.side_effect = Exception("Database connection failed")

        # Call the helper - should not raise, but return error status
        status, message = emit_artifact_comment(
            issue_id=1, adw_id="adw-error-test", artifact=artifact
        )

        # Verify error status
        assert status == "error"
        assert "Failed to insert comment" in message
        assert "Database connection failed" in message

    def test_emit_artifact_comment_no_database_call_when_issue_id_none(self):
        """Test that no database call is made when issue_id is None."""
        # Create a test artifact
        artifact = PlanArtifact(
            workflow_id="adw-skip-test",
            plan_data=PlanData(plan="Plan", summary="Summary"),
        )

        # Use patch to ensure create_comment is never called
        with patch("rouge.core.notifications.comments.create_comment") as mock_create:
            status, message = emit_artifact_comment(
                issue_id=None, adw_id="adw-skip-test", artifact=artifact
            )

            # Verify skipped
            assert status == "skipped"

            # Verify create_comment was never called
            mock_create.assert_not_called()

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_artifact_comment_preserves_artifact_metadata(self, mock_create_comment):
        """Test that artifact metadata like created_at is preserved in raw field."""
        # Create artifact with specific created_at time

        artifact = GitSetupArtifact(workflow_id="adw-meta-test", branch="main")

        mock_create_comment.return_value = Comment(
            id=1, issue_id=1, comment="test", adw_id="adw-meta-test"
        )

        emit_artifact_comment(issue_id=1, adw_id="adw-meta-test", artifact=artifact)

        call_args = mock_create_comment.call_args[0][0]
        artifact_json = call_args.raw["artifact"]

        # Verify metadata is present
        assert "created_at" in artifact_json
        assert "workflow_id" in artifact_json
        assert artifact_json["workflow_id"] == "adw-meta-test"
        assert artifact_json["branch"] == "main"


class TestEmitCommentFromPayload:
    """Tests for emit_comment_from_payload helper function."""

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_comment_from_payload_success(self, mock_create_comment):
        """Test emit_comment_from_payload creates comment successfully."""
        from rouge.core.models import CommentPayload

        payload = CommentPayload(
            issue_id=1,
            adw_id="adw-test",
            text="Test comment",
            source="system",
            kind="status",
        )

        mock_create_comment.return_value = Comment(
            id=10,
            issue_id=1,
            comment="Test comment",
            adw_id="adw-test",
        )

        status, message = emit_comment_from_payload(payload)

        assert status == "success"
        assert "Comment inserted" in message
        assert "ID=10" in message

    def test_emit_comment_from_payload_with_none_issue_id(self):
        """Test emit_comment_from_payload skips when issue_id is None."""
        from rouge.core.models import CommentPayload

        payload = CommentPayload(
            issue_id=None,
            adw_id="adw-test",
            text="Test comment",
            source="system",
            kind="status",
        )

        status, message = emit_comment_from_payload(payload)

        assert status == "skipped"
        assert "No issue_id" in message

    @patch("rouge.core.notifications.comments.create_comment")
    def test_emit_comment_from_payload_handles_error(self, mock_create_comment):
        """Test emit_comment_from_payload handles database errors."""
        from rouge.core.models import CommentPayload

        payload = CommentPayload(
            issue_id=1,
            adw_id="adw-test",
            text="Test comment",
            source="system",
            kind="status",
        )

        mock_create_comment.side_effect = Exception("Database error")

        status, message = emit_comment_from_payload(payload)

        assert status == "error"
        assert "Failed to insert comment" in message
