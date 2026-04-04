"""Tests for GlabPullRequestStep draft flag behavior.

Focuses on:
- Adding --draft flag when pipeline_type is 'thin'
- Omitting --draft flag when pipeline_type is 'full' or 'patch'
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.workflow.artifacts import ArtifactStore, ComposeRequestArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-glab-mr", base_path=tmp_path)


def _subprocess_side_effect(cmd: list[str], **kwargs: Any) -> MagicMock:
    """Simulate subprocess calls for glab MR creation flow."""
    result = MagicMock()
    if cmd[0] == "git" and cmd[1] == "rev-parse":
        result.returncode = 0
        result.stdout = "feature-branch"
    elif cmd[0] == "glab" and cmd[1] == "mr" and cmd[2] == "list":
        result.returncode = 0
        result.stdout = "[]"
    elif cmd[0] == "git" and cmd[1] == "push":
        result.returncode = 0
        result.stdout = ""
        result.stderr = ""
    elif cmd[0] == "glab" and cmd[1] == "mr" and cmd[2] == "create":
        result.returncode = 0
        result.stdout = "https://gitlab.com/org/repo/-/merge_requests/17"
    else:
        result.returncode = 0
        result.stdout = ""
    return result


def _make_context(store: ArtifactStore, pipeline_type: str) -> WorkflowContext:
    """Create a WorkflowContext with a compose-request artifact and the given pipeline_type."""
    compose_artifact = ComposeRequestArtifact(
        workflow_id="test-glab-mr",
        title="MR Title",
        summary="MR Summary",
        commits=[],
    )
    store.write_artifact(compose_artifact)

    return WorkflowContext(
        adw_id="test-glab-mr",
        issue_id=99,
        artifact_store=store,
        repo_paths=["/path/to/repo"],
        pipeline_type=pipeline_type,
    )


def _find_glab_create_cmd(mock_run: MagicMock) -> list[str]:
    """Extract the glab mr create command from mock_run call history."""
    glab_create_calls = [
        call
        for call in mock_run.call_args_list
        if call[0][0][0] == "glab" and call[0][0][2] == "create"
    ]
    assert (
        len(glab_create_calls) == 1
    ), f"Expected exactly 1 glab mr create call, got {len(glab_create_calls)}"
    return glab_create_calls[0][0][0]


class TestGlabPullRequestStepDraftFlag:
    """Tests verifying GlabPullRequestStep adds --draft flag based on pipeline_type."""

    @patch("rouge.core.workflow.steps.glab_pull_request_step._emit_and_log")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.os.environ", new_callable=dict)
    def test_thin_pipeline_includes_draft_flag(
        self,
        mock_environ,
        mock_run,
        _mock_log,
        mock_emit_artifact,
        mock_emit_and_log,
        store: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'thin', glab mr create command includes --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_emit_artifact.return_value = ("success", "ok")
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(store, pipeline_type="thin")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" in cmd_args

    @patch("rouge.core.workflow.steps.glab_pull_request_step._emit_and_log")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.os.environ", new_callable=dict)
    def test_full_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        _mock_log,
        mock_emit_artifact,
        mock_emit_and_log,
        store: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'full', glab mr create command does not include --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_emit_artifact.return_value = ("success", "ok")
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(store, pipeline_type="full")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" not in cmd_args

    @patch("rouge.core.workflow.steps.glab_pull_request_step._emit_and_log")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.emit_artifact_comment")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.log_artifact_comment_status")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.subprocess.run")
    @patch("rouge.core.workflow.steps.glab_pull_request_step.os.environ", new_callable=dict)
    def test_patch_pipeline_omits_draft_flag(
        self,
        mock_environ,
        mock_run,
        _mock_log,
        mock_emit_artifact,
        mock_emit_and_log,
        store: ArtifactStore,
    ) -> None:
        """When pipeline_type is 'patch', glab mr create command does not include --draft."""
        mock_environ["GITLAB_PAT"] = "fake-token"
        mock_emit_artifact.return_value = ("success", "ok")
        mock_run.side_effect = _subprocess_side_effect

        context = _make_context(store, pipeline_type="patch")

        step = GlabPullRequestStep()
        result = step.run(context)

        assert result.success is True
        cmd_args = _find_glab_create_cmd(mock_run)
        assert "--draft" not in cmd_args
