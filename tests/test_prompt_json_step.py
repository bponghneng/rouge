"""Tests for the declarative :class:`PromptJsonStep` executor.

These tests verify that the executor:

    * Loads the configured input artifact and extracts the configured field.
    * Executes a prompt and validates the JSON output for both supported
      schema kinds (``plan_chore_bug_feature`` and ``plan_task``).
    * Surfaces errors when the input artifact is missing
      (:class:`StepInputError`) or when JSON parsing/validation fails.
    * Writes a :class:`PlanArtifact` and emits a progress comment whose title
      is selected from the configured ``title_keys`` precedence.

The agent layer (``execute_template``) is mocked so no Claude call is
performed; comment emission helpers are also patched to avoid network
side effects.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from rouge.core.agents.claude import ClaudeAgentPromptResponse
from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.workflow.artifacts import (
    ArtifactStore,
    FetchIssueArtifact,
    FetchPatchArtifact,
)
from rouge.core.workflow.executors.prompt_json_step import (
    PromptJsonStep,
    PromptJsonStepSettings,
)
from rouge.core.workflow.step_base import WorkflowContext

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def issue() -> Issue:
    """Sample Issue used as the fetch-issue payload."""
    return Issue(
        id=7,
        description="Add a feature flag for the new dashboard",
        status="pending",
        type="full",
        adw_id="full-xyz",
        branch="feature/dashboard-flag",
    )


@pytest.fixture
def patch_issue() -> Issue:
    """Sample Issue used as the fetch-patch payload."""
    return Issue(
        id=11,
        description="Fix off-by-one in pagination helper",
        status="pending",
        type="patch",
        adw_id="patch-xyz",
        branch="fix/pagination",
    )


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    return ArtifactStore(workflow_id="adw-prompt-json", base_path=tmp_path)


@pytest.fixture
def context_with_issue(issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Workflow context with a fetch-issue artifact written to the store."""
    artifact = FetchIssueArtifact(workflow_id=store.workflow_id, issue=issue)
    store.write_artifact(artifact)
    return WorkflowContext(
        issue_id=issue.id,
        adw_id=store.workflow_id,
        artifact_store=store,
    )


@pytest.fixture
def context_with_patch(patch_issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Workflow context with a fetch-patch artifact written to the store."""
    artifact = FetchPatchArtifact(workflow_id=store.workflow_id, patch=patch_issue)
    store.write_artifact(artifact)
    return WorkflowContext(
        issue_id=patch_issue.id,
        adw_id=store.workflow_id,
        artifact_store=store,
    )


@pytest.fixture
def context_without_artifact(store: ArtifactStore) -> WorkflowContext:
    """Workflow context with no artifacts written."""
    return WorkflowContext(
        issue_id=99,
        adw_id=store.workflow_id,
        artifact_store=store,
    )


def _chore_settings() -> PromptJsonStepSettings:
    return PromptJsonStepSettings(
        prompt_id=PromptId.THIN_PLAN,
        input_artifact="fetch-issue",
        input_field="issue",
        json_schema_kind="plan_chore_bug_feature",
        title_keys=["chore", "bug", "feature"],
    )


def _task_settings() -> PromptJsonStepSettings:
    return PromptJsonStepSettings(
        prompt_id=PromptId.CLAUDE_CODE_PLAN,
        input_artifact="fetch-issue",
        input_field="issue",
        json_schema_kind="plan_task",
        title_keys=["task"],
    )


def _patch_settings() -> PromptJsonStepSettings:
    return PromptJsonStepSettings(
        prompt_id=PromptId.PATCH_PLAN,
        input_artifact="fetch-patch",
        input_field="patch",
        json_schema_kind="plan_chore_bug_feature",
        title_keys=["chore", "bug", "feature"],
    )


def _agent_response(parsed: dict) -> ClaudeAgentPromptResponse:
    """Build a successful Claude agent response from a parsed-JSON dict."""
    return ClaudeAgentPromptResponse(
        output=json.dumps(parsed),
        success=True,
        session_id="sess-prompt-json",
    )


# ---------------------------------------------------------------------------
# Happy paths for both schema kinds
# ---------------------------------------------------------------------------


class TestPromptJsonStepHappyPaths:
    """Both supported schema kinds produce a PlanArtifact and a comment."""

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_chore_bug_feature_schema_writes_plan_artifact(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_issue,
    ) -> None:
        parsed = {
            "type": "feature",
            "output": "plan",
            "plan": "## Plan\nSteps go here",
            "summary": "Add the feature flag",
            "feature": "Add dashboard flag",
        }
        mock_execute.return_value = _agent_response(parsed)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_chore_settings())
        result = step.run(context_with_issue)

        assert result.success is True
        assert context_with_issue.artifact_store.artifact_exists("plan")

        # Title comes from the first match in title_keys (here, "feature").
        payload = mock_emit.call_args[0][0]
        assert "Add dashboard flag" in payload.text
        assert "Add the feature flag" in payload.text  # summary appended

        # Cached plan_data on the context so legacy code keeps working.
        plan_data = context_with_issue.data["plan_data"]
        assert plan_data.plan == parsed["plan"]
        assert plan_data.summary == parsed["summary"]
        assert plan_data.session_id == "sess-prompt-json"

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_plan_task_schema_writes_plan_artifact(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_issue,
    ) -> None:
        parsed = {
            "task": "Wire feature flag",
            "output": "plan",
            "plan": "## Plan\nSteps go here",
            "summary": "Plan summary",
        }
        mock_execute.return_value = _agent_response(parsed)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_task_settings())
        result = step.run(context_with_issue)

        assert result.success is True
        assert context_with_issue.artifact_store.artifact_exists("plan")

        # Title is taken from the configured "task" key.
        payload = mock_emit.call_args[0][0]
        assert "Wire feature flag" in payload.text
        assert "Plan summary" in payload.text

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_patch_input_artifact(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_patch,
    ) -> None:
        """``input_artifact='fetch-patch'`` reads the patch issue."""
        parsed = {
            "type": "bug",
            "output": "plan",
            "plan": "## Plan\nFix it",
            "summary": "Patch the bug",
            "bug": "Fix off-by-one",
        }
        mock_execute.return_value = _agent_response(parsed)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_patch_settings())
        result = step.run(context_with_patch)

        assert result.success is True
        assert context_with_patch.artifact_store.artifact_exists("plan")
        # The agent request was built from the patch description.
        agent_request = mock_execute.call_args[0][0]
        assert agent_request.args == ["Fix off-by-one in pagination helper"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


class TestPromptJsonStepErrors:
    """Error paths return failed StepResult and avoid writing the artifact."""

    def test_missing_input_artifact_returns_failure(self, context_without_artifact) -> None:
        """When the configured input artifact is absent, the step fails."""
        step = PromptJsonStep(settings=_chore_settings())
        result = step.run(context_without_artifact)

        assert result.success is False
        # ``load_required_artifact`` raises StepInputError, which the step
        # catches and surfaces in its error message.
        assert "Cannot run" in result.error
        assert "fetch-issue" in result.error
        assert not context_without_artifact.artifact_store.artifact_exists("plan")

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_invalid_json_output_returns_failure(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_issue,
    ) -> None:
        """A non-JSON agent output is surfaced as a failure with no artifact."""
        mock_execute.return_value = ClaudeAgentPromptResponse(
            output="not valid json at all",
            success=True,
            session_id="sess-bad",
        )
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_chore_settings())
        result = step.run(context_with_issue)

        assert result.success is False
        assert result.error is not None
        # parse_and_validate_json reports invalid JSON / decode errors.
        assert "Invalid JSON" in result.error or "JSON" in result.error
        assert not context_with_issue.artifact_store.artifact_exists("plan")

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_agent_failure_returns_failure(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_issue,
    ) -> None:
        """When the agent reports failure, the step fails without writing."""
        mock_execute.return_value = ClaudeAgentPromptResponse(
            output="agent broke",
            success=False,
            session_id=None,
        )
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_chore_settings())
        result = step.run(context_with_issue)

        assert result.success is False
        assert "agent broke" in result.error
        assert not context_with_issue.artifact_store.artifact_exists("plan")

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_missing_required_field_returns_failure(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_issue,
    ) -> None:
        """A JSON payload missing a required field surfaces a failure."""
        # Missing "plan" key — required by plan_chore_bug_feature schema.
        parsed = {
            "type": "chore",
            "output": "plan",
            "summary": "Do the chore",
        }
        mock_execute.return_value = _agent_response(parsed)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_chore_settings())
        result = step.run(context_with_issue)

        assert result.success is False
        assert result.error is not None
        assert not context_with_issue.artifact_store.artifact_exists("plan")


# ---------------------------------------------------------------------------
# Title-key precedence
# ---------------------------------------------------------------------------


class TestPromptJsonStepTitleKeys:
    """The progress-comment title is picked from ``title_keys`` in order."""

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_title_picks_first_non_empty_key(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_issue,
    ) -> None:
        parsed = {
            "type": "chore",
            "output": "plan",
            "plan": "## Plan",
            "summary": "summary",
            "chore": "Tidy README",
            "bug": "should not be picked",
        }
        mock_execute.return_value = _agent_response(parsed)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_chore_settings())
        result = step.run(context_with_issue)

        assert result.success is True
        payload = mock_emit.call_args[0][0]
        # First match in ["chore", "bug", "feature"] wins.
        assert payload.text.startswith("Tidy README")

    @patch("rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload")
    @patch("rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment")
    @patch("rouge.core.workflow.executors.prompt_json_step.execute_template")
    def test_title_falls_back_when_no_keys_match(
        self,
        mock_execute,
        mock_emit_artifact,
        mock_emit,
        context_with_issue,
    ) -> None:
        # No title_keys present in the parsed payload.
        parsed = {
            "type": "chore",
            "output": "plan",
            "plan": "## Plan",
            "summary": "summary",
        }
        mock_execute.return_value = _agent_response(parsed)
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit.return_value = ("success", "ok")

        step = PromptJsonStep(settings=_chore_settings())
        result = step.run(context_with_issue)

        assert result.success is True
        payload = mock_emit.call_args[0][0]
        assert "Implementation plan created" in payload.text


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


class TestPromptJsonStepProperties:
    def test_default_display_name(self) -> None:
        step = PromptJsonStep(settings=_chore_settings())
        assert step.name == "Building implementation plan"

    def test_display_name_override(self) -> None:
        step = PromptJsonStep(
            settings=_chore_settings(),
            display_name="Building patch plan",
        )
        assert step.name == "Building patch plan"

    def test_display_name_setter(self) -> None:
        step = PromptJsonStep(settings=_chore_settings())
        step.name = "Custom"
        assert step.name == "Custom"

    def test_step_is_critical(self) -> None:
        step = PromptJsonStep(settings=_chore_settings())
        assert step.is_critical is True
