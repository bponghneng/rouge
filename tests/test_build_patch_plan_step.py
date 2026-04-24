"""Tests for PatchPlanStep workflow step.

After the Phase 5 refactor, PatchPlanStep is a zero-argument shim that
subclasses :class:`PromptJsonStep` with the built-in patch-plan
configuration.  These tests verify the shim preserves the original behaviour
of the legacy step: it loads the patch issue from the fetch-patch artifact
and writes a :class:`PlanArtifact` (not a PatchPlanArtifact).
"""

from pathlib import Path
from typing import Generator
from unittest.mock import patch

import pytest

from rouge.core.agents.claude import ClaudeAgentPromptResponse
from rouge.core.models import Issue
from rouge.core.prompts import PromptId
from rouge.core.workflow.artifacts import ArtifactStore, FetchPatchArtifact
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.patch_plan_step import PatchPlanStep


@pytest.fixture
def patch_issue() -> Issue:
    """Create a sample patch issue."""
    return Issue(
        id=10,
        description="Fix typo in README and update documentation links",
        status="pending",
        type="patch",
        adw_id="patch-abc123",
        branch="patch/fix-typo",
    )


@pytest.fixture
def store(tmp_path: Path) -> ArtifactStore:
    """Create a temporary artifact store."""
    return ArtifactStore(workflow_id="test-adw-patch-plan", base_path=tmp_path)


@pytest.fixture
def context_with_artifact(patch_issue: Issue, store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context with fetch-patch artifact written to the store."""
    artifact = FetchPatchArtifact(
        workflow_id=store.workflow_id,
        patch=patch_issue,
    )
    store.write_artifact(artifact)
    return WorkflowContext(
        issue_id=10,
        adw_id="test-adw-patch-plan",
        artifact_store=store,
    )


@pytest.fixture
def context_without_artifact(store: ArtifactStore) -> WorkflowContext:
    """Create a workflow context WITHOUT fetch-patch artifact."""
    return WorkflowContext(
        issue_id=10,
        adw_id="test-adw-patch-plan",
        artifact_store=store,
    )


def _make_response(
    *,
    success: bool,
    output: str,
    session_id: str | None = "sess-1",
) -> ClaudeAgentPromptResponse:
    """Build a ClaudeAgentPromptResponse for mocking execute_template."""
    return ClaudeAgentPromptResponse(
        output=output,
        success=success,
        session_id=session_id,
    )


@pytest.fixture
def patched_executor() -> Generator[dict, None, None]:
    """Patch helpers and execute_template inside the PromptJsonStep executor module."""
    with (
        patch("rouge.core.workflow.executors.prompt_json_step.execute_template") as mock_execute,
        patch(
            "rouge.core.workflow.executors.prompt_json_step.emit_artifact_comment"
        ) as mock_emit_artifact,
        patch(
            "rouge.core.workflow.executors.prompt_json_step.emit_comment_from_payload"
        ) as mock_emit_payload,
        patch("rouge.core.workflow.executors.prompt_json_step.log_artifact_comment_status"),
    ):
        mock_emit_artifact.return_value = ("success", "ok")
        mock_emit_payload.return_value = ("success", "ok")
        yield {
            "execute_template": mock_execute,
            "emit_artifact_comment": mock_emit_artifact,
            "emit_comment_from_payload": mock_emit_payload,
        }


class TestBuildPatchPlanStepLoadsFromArtifact:
    """Tests verifying PatchPlanStep loads the issue from fetch-patch artifact."""

    def test_loads_issue_from_fetch_patch_artifact(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
        patch_issue: Issue,
    ) -> None:
        """Step loads the patch issue from the fetch-patch artifact, not context.issue."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"type": "bug", "output": "plan", '
                '"plan": "## Patch Plan\\nFix typo", '
                '"summary": "Plan for patch: Fix typo in README"}'
            ),
        )

        step = PatchPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        # Verify execute_template was called with the patch issue description.
        request = patched_executor["execute_template"].call_args.args[0]
        assert request.prompt_id == PromptId.PATCH_PLAN
        assert request.args == [patch_issue.description]
        assert request.issue_id == patch_issue.id

    def test_succeeds_when_context_issue_is_none_but_artifact_present(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step succeeds even when context.issue is None if fetch-patch artifact exists."""
        # Explicitly leave context.issue as None (the default).
        assert context_with_artifact.issue is None

        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"type": "chore", "output": "plan", '
                '"plan": "## Plan\\nDo the thing", "summary": "Summary"}'
            ),
        )

        step = PatchPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True

    def test_fails_when_fetch_patch_artifact_missing(
        self,
        context_without_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step fails when fetch-patch artifact is absent (required dependency)."""
        step = PatchPlanStep()
        result = step.run(context_without_artifact)

        assert result.success is False
        assert result.error is not None
        assert "fetch-patch" in result.error

    def test_saves_plan_artifact_not_patch_plan_artifact(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step saves a PlanArtifact (not a PatchPlanArtifact)."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"type": "feature", "output": "plan", '
                '"plan": "## Plan\\nDo the thing", '
                '"summary": "Plan for patch: Fix typo"}'
            ),
        )

        step = PatchPlanStep()
        result = step.run(context_with_artifact)

        assert result.success is True
        # Verify the artifact saved is a PlanArtifact.
        assert context_with_artifact.artifact_store.artifact_exists("plan")

    def test_does_not_read_other_artifacts(
        self,
        context_with_artifact: WorkflowContext,
        patched_executor: dict,
    ) -> None:
        """Step reads only the fetch-patch artifact, not fetch-issue or plan artifacts."""
        patched_executor["execute_template"].return_value = _make_response(
            success=True,
            output=(
                '{"type": "chore", "output": "plan", '
                '"plan": "## Plan\\nFix", "summary": "Fix things"}'
            ),
        )

        read_calls: list[str] = []
        original_read = context_with_artifact.artifact_store.read_artifact

        def tracking_read(artifact_type: str, model_class: object = None) -> object:
            read_calls.append(artifact_type)
            return original_read(artifact_type, model_class)

        with patch.object(
            context_with_artifact.artifact_store,
            "read_artifact",
            side_effect=tracking_read,
        ):
            step = PatchPlanStep()
            step.run(context_with_artifact)

        # Only fetch-patch should be read.
        assert "fetch-issue" not in read_calls
        assert "plan" not in read_calls
        # fetch-patch may be read (it's the declared dependency).
        assert all(t == "fetch-patch" for t in read_calls)


class TestBuildPatchPlanStepProperties:
    """Tests for PatchPlanStep properties."""

    def test_step_name(self) -> None:
        """Test step has correct name."""
        step = PatchPlanStep()
        assert step.name == "Building patch plan"

    def test_step_is_critical(self) -> None:
        """Test step is critical."""
        step = PatchPlanStep()
        assert step.is_critical is True

    def test_step_id(self) -> None:
        """Step exposes the patch-plan slug as ``step_id``."""
        step = PatchPlanStep()
        assert step.step_id == "patch-plan"
