"""Unit tests for :func:`rouge.core.workflow.resolver.resolve_workflow`."""

from __future__ import annotations

from typing import Any

import pytest

from rouge.core.prompts import PromptId
from rouge.core.workflow.config import (
    LegacyStepConfig,
    WorkflowConfig,
)
from rouge.core.workflow.executors.prompt_json_step import PromptJsonStep
from rouge.core.workflow.resolver import resolve_workflow
from rouge.core.workflow.step_base import WorkflowStep
from rouge.core.workflow.steps.fetch_issue_step import FetchIssueStep
from rouge.core.workflow.steps.implement_step import ImplementPlanStep


def _prompt_json_data(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid ``PromptJsonStepConfig`` payload."""
    base: dict[str, Any] = {
        "kind": "prompt-json",
        "step_id": "plan-step",
        "display_name": "Plan Step",
        "prompt_id": PromptId.CLAUDE_CODE_PLAN.value,
        "agent_name": "planner",
        "json_schema": "plan_schema",
        "required_fields": {"plan": "str"},
        "issue_binding": "fetch-issue",
        "output_artifact": "plan",
    }
    base.update(overrides)
    return base


def _legacy_data(**overrides: Any) -> dict[str, Any]:
    """Return a minimal valid ``LegacyStepConfig`` payload pointing at FetchIssueStep."""
    base: dict[str, Any] = {
        "kind": "legacy",
        "step_id": "fetch-issue",
        "display_name": "Fetch Issue",
        "import_path": ("rouge.core.workflow.steps.fetch_issue_step:FetchIssueStep"),
    }
    base.update(overrides)
    return base


class TestPromptJsonStepResolution:
    """Resolving a config with a PromptJsonStepConfig entry."""

    def test_returns_prompt_json_step_instance(self) -> None:
        """A prompt-json entry yields a single PromptJsonStep with matching metadata."""
        cfg = WorkflowConfig(
            type_id="test",
            steps=[_prompt_json_data(step_id="plan-step", display_name="Plan Step")],
        )
        steps = resolve_workflow(cfg)

        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, PromptJsonStep)
        assert step.step_id == "plan-step"
        assert step.name == "Plan Step"


class TestLegacyStepResolution:
    """Resolving a config with LegacyStepConfig entries."""

    def test_returns_legacy_class_instance(self) -> None:
        """The resolver imports and instantiates the referenced class."""
        cfg = WorkflowConfig(
            type_id="test",
            steps=[_legacy_data(step_id="fetch-issue")],
        )
        steps = resolve_workflow(cfg)

        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, FetchIssueStep)

    def test_init_kwargs_are_forwarded(self) -> None:
        """``init_kwargs`` are passed to the step class constructor as kwargs."""
        cfg = WorkflowConfig(
            type_id="test",
            steps=[
                _legacy_data(
                    step_id="implement-plan",
                    display_name="Implement Plan",
                    import_path=("rouge.core.workflow.steps.implement_step:ImplementPlanStep"),
                    init_kwargs={"plan_step_id": "thin-plan"},
                )
            ],
        )
        steps = resolve_workflow(cfg)

        assert len(steps) == 1
        step = steps[0]
        assert isinstance(step, ImplementPlanStep)
        assert step.plan_step_id == "thin-plan"


class TestLegacyImportFailures:
    """Error handling around malformed or unresolvable import paths."""

    def test_missing_colon_raises_value_error(self) -> None:
        """Pydantic rejects import_path with no colon before resolver runs."""
        # The config-level validator catches this. We assert that the
        # validator raises so that such an invalid config never reaches the
        # resolver. The resolver itself also guards defensively.
        with pytest.raises(Exception) as exc_info:
            WorkflowConfig(
                type_id="test",
                steps=[
                    _legacy_data(
                        step_id="bad-step",
                        import_path="rouge.core.workflow.steps.fetch_issue_step.FetchIssueStep",
                    )
                ],
            )
        assert "import_path" in str(exc_info.value)

    def test_defensive_missing_colon_on_direct_config_raises(self) -> None:
        """Directly constructed LegacyStepConfig with bad path is rejected."""
        # Same as above but exercises the defensive guard by bypassing the
        # WorkflowConfig wrapper. Pydantic still catches it.
        with pytest.raises(Exception) as exc_info:
            LegacyStepConfig(
                kind="legacy",
                step_id="bad-step",
                display_name="Bad",
                import_path="no_colon_here",
            )
        assert "import_path" in str(exc_info.value)

    def test_unknown_module_raises_value_error(self) -> None:
        """A syntactically valid but unimportable module path yields ValueError."""
        cfg = WorkflowConfig(
            type_id="test",
            steps=[
                _legacy_data(
                    step_id="bad-mod",
                    import_path="rouge.does.not.exist:SomeStep",
                )
            ],
        )
        with pytest.raises(ValueError) as exc_info:
            resolve_workflow(cfg)
        assert "bad-mod" in str(exc_info.value)

    def test_unknown_class_raises_value_error(self) -> None:
        """A valid module but missing class attribute yields ValueError."""
        cfg = WorkflowConfig(
            type_id="test",
            steps=[
                _legacy_data(
                    step_id="bad-cls",
                    import_path=("rouge.core.workflow.steps.fetch_issue_step:NotARealClass"),
                )
            ],
        )
        with pytest.raises(ValueError) as exc_info:
            resolve_workflow(cfg)
        assert "bad-cls" in str(exc_info.value)

    def test_class_not_workflow_step_raises(self) -> None:
        """A resolved class that is not a WorkflowStep subclass is rejected."""
        cfg = WorkflowConfig(
            type_id="test",
            steps=[
                _legacy_data(
                    step_id="not-a-step",
                    import_path="builtins:dict",
                )
            ],
        )
        with pytest.raises(ValueError) as exc_info:
            resolve_workflow(cfg)
        message = str(exc_info.value)
        assert "not-a-step" in message
        assert "WorkflowStep" in message


class TestPlatformGate:
    """Platform-gate filtering honors DEV_SEC_OPS_PLATFORM."""

    @staticmethod
    def _build_gated_config() -> WorkflowConfig:
        """Build a workflow with one non-gated step and two platform-gated steps."""
        return WorkflowConfig(
            type_id="test",
            steps=[
                _legacy_data(
                    step_id="fetch-issue",
                    import_path=("rouge.core.workflow.steps.fetch_issue_step:FetchIssueStep"),
                ),
                _legacy_data(
                    step_id="gh-pull-request",
                    display_name="Gh PR",
                    import_path=(
                        "rouge.core.workflow.steps.gh_pull_request_step:" "GhPullRequestStep"
                    ),
                ),
                _legacy_data(
                    step_id="glab-pull-request",
                    display_name="Glab PR",
                    import_path=(
                        "rouge.core.workflow.steps.glab_pull_request_step:" "GlabPullRequestStep"
                    ),
                ),
            ],
            platform_gate={
                "github": ["gh-pull-request"],
                "gitlab": ["glab-pull-request"],
            },
        )

    def test_github_active_keeps_github_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When DEV_SEC_OPS_PLATFORM=github, only the github gated step survives."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        cfg = self._build_gated_config()
        steps = resolve_workflow(cfg)

        slugs = [s.step_id for s in steps]
        assert "fetch-issue" in slugs
        assert "gh-pull-request" in slugs
        assert "glab-pull-request" not in slugs

    def test_gitlab_active_keeps_gitlab_step(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When DEV_SEC_OPS_PLATFORM=gitlab, only the gitlab gated step survives."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        cfg = self._build_gated_config()
        steps = resolve_workflow(cfg)

        slugs = [s.step_id for s in steps]
        assert "fetch-issue" in slugs
        assert "glab-pull-request" in slugs
        assert "gh-pull-request" not in slugs

    def test_platform_unset_drops_all_gated_steps(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """With DEV_SEC_OPS_PLATFORM unset, all gated steps are filtered out."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        cfg = self._build_gated_config()
        steps = resolve_workflow(cfg)

        slugs = [s.step_id for s in steps]
        assert slugs == ["fetch-issue"]

    def test_platform_gate_none_applies_no_filtering(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When platform_gate is None, every step is retained regardless of env."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        cfg = WorkflowConfig(
            type_id="test",
            steps=[
                _legacy_data(
                    step_id="fetch-issue",
                    import_path=("rouge.core.workflow.steps.fetch_issue_step:FetchIssueStep"),
                ),
                _legacy_data(
                    step_id="gh-pull-request",
                    display_name="Gh PR",
                    import_path=(
                        "rouge.core.workflow.steps.gh_pull_request_step:" "GhPullRequestStep"
                    ),
                ),
            ],
            platform_gate=None,
        )
        steps = resolve_workflow(cfg)

        slugs = [s.step_id for s in steps]
        assert slugs == ["fetch-issue", "gh-pull-request"]


class TestResolverReturnsWorkflowSteps:
    """Smoke-test that resolved entries are always WorkflowStep subclasses."""

    def test_all_entries_are_workflow_steps(self) -> None:
        """Every resolved element must be a WorkflowStep instance."""
        cfg = WorkflowConfig(
            type_id="test",
            steps=[
                _legacy_data(step_id="fetch-issue"),
                _prompt_json_data(step_id="plan-step"),
            ],
        )
        steps = resolve_workflow(cfg)
        assert len(steps) == 2
        for step in steps:
            assert isinstance(step, WorkflowStep)
