"""Tests for :class:`PromptJsonStep` config-driven workflow step executor.

The executor is exercised end-to-end with :func:`execute_template` and the
comment-emission helpers patched so only the executor's orchestration logic
is under test.
"""

from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock, patch

import pytest

from rouge.core.agents.claude import ClaudeAgentPromptResponse
from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.workflow.artifacts import (
    ArtifactStore,
    FetchIssueArtifact,
    PlanArtifact,
)
from rouge.core.workflow.config import PromptJsonStepConfig
from rouge.core.workflow.executors.prompt_json_step import PromptJsonStep
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.types import PlanData

# Schema copied verbatim from ClaudeCodePlanStep for parity testing.
PLAN_REQUIRED_FIELDS = {
    "task": "str",
    "output": "str",
    "plan": "str",
    "summary": "str",
}

PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "task": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["task", "output", "plan", "summary"]
}"""


@pytest.fixture
def issue() -> Issue:
    """Create a sample issue matching the full-workflow shape."""
    return Issue(
        id=42,
        description="Add dark mode toggle to settings page",
        status="pending",
        type="full",
        adw_id="full-abc123",
        branch="feature/dark-mode",
    )


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Create an isolated artifact store for each test."""
    return ArtifactStore(workflow_id="test-adw-prompt-json", base_path=tmp_path)


@pytest.fixture
def context_with_issue(issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Workflow context populated with a FetchIssueArtifact on disk."""
    artifact = FetchIssueArtifact(workflow_id=store.workflow_id, issue=issue)
    store.write_artifact(artifact)
    return WorkflowContext(
        issue_id=42,
        adw_id=store.workflow_id,
        artifact_store=store,
    )


@pytest.fixture
def context_without_issue(store: ArtifactStore) -> WorkflowContext:
    """Workflow context WITHOUT the fetch-issue artifact."""
    return WorkflowContext(
        issue_id=42,
        adw_id=store.workflow_id,
        artifact_store=store,
    )


@pytest.fixture
def plan_config() -> PromptJsonStepConfig:
    """Config matching ClaudeCodePlanStep's behavior (task-keyed schema)."""
    return PromptJsonStepConfig(
        step_id="claude-code-plan",
        display_name="Building task-oriented implementation plan",
        critical=True,
        outputs=["plan"],
        inputs=[],
        prompt_id=PromptId.CLAUDE_CODE_PLAN,
        agent_name="sdlc_planner",
        model="sonnet",
        json_schema=PLAN_JSON_SCHEMA,
        required_fields=PLAN_REQUIRED_FIELDS,
        issue_binding="fetch-issue",
        output_artifact="plan",
        rerun_target="fetch-issue",
    )


@pytest.fixture
def patched_executor_helpers() -> Generator[dict, None, None]:
    """Patch comment helpers and execute_template in the executor module."""
    with (
        patch("rouge.core.workflow.executors.prompt_json_step.execute_template") as mock_execute,
        patch(
            "rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment"
        ) as mock_emit_artifact,
        patch(
            "rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload"
        ) as mock_emit_payload,
        patch(
            "rouge.core.workflow.executors.prompt_json_step.log_artifact_comment_status"
        ) as mock_log_status,
    ):
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit_payload.return_value = ("success", "ok")
        yield {
            "execute_template": mock_execute,
            "emit_artifact_comment": mock_emit_artifact,
            "emit_comment_from_payload": mock_emit_payload,
            "log_artifact_comment_status": mock_log_status,
        }


def _make_response(
    *,
    success: bool,
    output: str,
    session_id: str | None = "sess-xyz",
) -> ClaudeAgentPromptResponse:
    """Build a ClaudeAgentPromptResponse for mocking execute_template."""
    return ClaudeAgentPromptResponse(
        output=output,
        success=success,
        session_id=session_id,
    )


class TestPromptJsonStepHappyPath:
    """Tests covering the nominal successful execution."""

    def test_happy_path(
        self,
        context_with_issue: WorkflowContext,
        plan_config: PromptJsonStepConfig,
        patched_executor_helpers: dict,
        issue: Issue,
    ) -> None:
        """Valid JSON produces a PlanArtifact and emits progress comments."""
        parsed = {
            "task": "Add dark mode toggle",
            "output": "plan",
            "plan": "## Plan\n- step one\n- step two",
            "summary": "Dark mode summary",
        }
        mock_execute: MagicMock = patched_executor_helpers["execute_template"]
        mock_execute.return_value = _make_response(
            success=True,
            output=(
                '{"task": "Add dark mode toggle", "output": "plan", '
                '"plan": "## Plan\\n- step one\\n- step two", '
                '"summary": "Dark mode summary"}'
            ),
            session_id="sess-xyz",
        )

        step = PromptJsonStep(plan_config)
        result = step.run(context_with_issue)

        assert result.success is True
        assert result.error is None

        # execute_template called with expected request fields.
        mock_execute.assert_called_once()
        sent_request = mock_execute.call_args.args[0]
        assert sent_request.prompt_id == PromptId.CLAUDE_CODE_PLAN
        assert sent_request.agent_name == "sdlc_planner"
        assert sent_request.model == "sonnet"
        assert sent_request.json_schema == PLAN_JSON_SCHEMA
        assert sent_request.args == [issue.description]
        assert sent_request.adw_id == context_with_issue.adw_id
        assert sent_request.issue_id == issue.id

        # PlanArtifact written with expected fields.
        assert context_with_issue.artifact_store.artifact_exists("plan")
        saved = context_with_issue.artifact_store.read_artifact("plan")
        assert isinstance(saved, PlanArtifact)
        assert saved.plan_data.plan == parsed["plan"]
        assert saved.plan_data.summary == parsed["summary"]
        assert saved.plan_data.session_id == "sess-xyz"

        # plan_data mirrored into context.
        assert context_with_issue.data["plan_data"].plan == parsed["plan"]

        # Progress comment emitted with the task title in the text.
        mock_emit_payload: MagicMock = patched_executor_helpers["emit_comment_from_payload"]
        mock_emit_artifact: MagicMock = patched_executor_helpers["emit_artifact_comment"]
        mock_emit_artifact.assert_called_once()
        mock_emit_payload.assert_called_once()
        payload = mock_emit_payload.call_args.args[0]
        assert "Add dark mode toggle" in payload.text
        assert "Dark mode summary" in payload.text
        assert payload.raw["parsed"] == parsed


class TestPromptJsonStepFailureCases:
    """Tests covering error paths."""

    def test_missing_required_artifact(
        self,
        context_without_issue: WorkflowContext,
        plan_config: PromptJsonStepConfig,
        patched_executor_helpers: dict,
    ) -> None:
        """Missing FetchIssueArtifact yields failure mentioning the artifact."""
        step = PromptJsonStep(plan_config)
        result = step.run(context_without_issue)

        assert result.success is False
        assert result.error is not None
        assert "fetch-issue" in result.error
        # rerun_target honored when set.
        assert result.rerun_from == plan_config.rerun_target

        # Agent was never called because input loading failed first.
        mock_execute: MagicMock = patched_executor_helpers["execute_template"]
        mock_execute.assert_not_called()

    def test_missing_required_artifact_no_rerun_target(
        self,
        context_without_issue: WorkflowContext,
        patched_executor_helpers: dict,
    ) -> None:
        """When rerun_target is None the fail result has no rerun_from."""
        config = PromptJsonStepConfig(
            step_id="claude-code-plan",
            display_name="Building task-oriented implementation plan",
            critical=True,
            outputs=["plan"],
            inputs=[],
            prompt_id=PromptId.CLAUDE_CODE_PLAN,
            agent_name="sdlc_planner",
            model="sonnet",
            json_schema=PLAN_JSON_SCHEMA,
            required_fields=PLAN_REQUIRED_FIELDS,
            issue_binding="fetch-issue",
            output_artifact="plan",
            rerun_target=None,
        )
        step = PromptJsonStep(config)
        result = step.run(context_without_issue)

        assert result.success is False
        assert result.rerun_from is None

    def test_agent_failure(
        self,
        context_with_issue: WorkflowContext,
        plan_config: PromptJsonStepConfig,
        patched_executor_helpers: dict,
    ) -> None:
        """execute_template returning success=False surfaces as failure."""
        mock_execute: MagicMock = patched_executor_helpers["execute_template"]
        mock_execute.return_value = _make_response(success=False, output="boom")

        step = PromptJsonStep(plan_config)
        result = step.run(context_with_issue)

        assert result.success is False
        assert result.error == "boom"
        assert result.rerun_from == plan_config.rerun_target
        assert not context_with_issue.artifact_store.artifact_exists("plan")

    def test_empty_agent_output(
        self,
        context_with_issue: WorkflowContext,
        plan_config: PromptJsonStepConfig,
        patched_executor_helpers: dict,
    ) -> None:
        """Successful response with empty output is treated as a failure."""
        mock_execute: MagicMock = patched_executor_helpers["execute_template"]
        mock_execute.return_value = _make_response(success=True, output="")

        step = PromptJsonStep(plan_config)
        result = step.run(context_with_issue)

        assert result.success is False
        assert result.error is not None
        assert "No output" in result.error
        assert result.rerun_from == plan_config.rerun_target

    def test_invalid_json(
        self,
        context_with_issue: WorkflowContext,
        plan_config: PromptJsonStepConfig,
        patched_executor_helpers: dict,
    ) -> None:
        """Malformed JSON from agent surfaces as a parse failure."""
        mock_execute: MagicMock = patched_executor_helpers["execute_template"]
        mock_execute.return_value = _make_response(
            success=True,
            output="not-json-at-all",
        )

        step = PromptJsonStep(plan_config)
        result = step.run(context_with_issue)

        assert result.success is False
        assert result.error is not None
        assert result.rerun_from == plan_config.rerun_target
        assert not context_with_issue.artifact_store.artifact_exists("plan")


class TestPromptJsonStepParity:
    """Parity with the existing ClaudeCodePlanStep implementation."""

    def test_plan_artifact_matches_claude_code_plan_step(
        self,
        context_with_issue: WorkflowContext,
        plan_config: PromptJsonStepConfig,
        patched_executor_helpers: dict,
    ) -> None:
        """PromptJsonStep's PlanArtifact matches ClaudeCodePlanStep output."""
        parsed = {
            "task": "Parity task",
            "output": "plan",
            "plan": "## Plan\n- single step",
            "summary": "Parity summary",
        }
        mock_execute: MagicMock = patched_executor_helpers["execute_template"]
        mock_execute.return_value = _make_response(
            success=True,
            output=(
                '{"task": "Parity task", "output": "plan", '
                '"plan": "## Plan\\n- single step", '
                '"summary": "Parity summary"}'
            ),
            session_id="sess-parity",
        )

        step = PromptJsonStep(plan_config)
        result = step.run(context_with_issue)
        assert result.success is True

        saved = context_with_issue.artifact_store.read_artifact("plan")
        assert isinstance(saved, PlanArtifact)

        # Build the expected artifact the same way ClaudeCodePlanStep does.
        expected = PlanArtifact(
            workflow_id=context_with_issue.adw_id,
            plan_data=PlanData(
                plan=parsed["plan"],
                summary=parsed["summary"],
                session_id="sess-parity",
            ),
        )

        assert saved.plan_data.plan == expected.plan_data.plan
        assert saved.plan_data.summary == expected.plan_data.summary
        assert saved.plan_data.session_id == expected.plan_data.session_id


class TestPromptJsonStepConstruction:
    """Tests for fail-fast construction behavior."""

    def test_unknown_output_artifact_raises_value_error(self) -> None:
        """Constructing with an artifact lacking a builder raises ValueError."""
        # ``compose-commits`` has no payload builder registered by default.
        config = PromptJsonStepConfig(
            step_id="compose-commits",
            display_name="Composing commits",
            critical=True,
            outputs=["compose-commits"],
            inputs=[],
            prompt_id=PromptId.COMPOSE_COMMITS,
            agent_name="commit_composer",
            model="sonnet",
            json_schema="{}",
            required_fields={"summary": "str"},
            issue_binding="fetch-issue",
            output_artifact="compose-commits",
            rerun_target=None,
        )
        with pytest.raises(ValueError, match="No payload builder registered"):
            PromptJsonStep(config)
