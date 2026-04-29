"""Unit tests for :func:`rouge.core.workflow.config_resolver.resolve_workflow`.

The resolver is the bridge between :class:`WorkflowConfig` and the runnable
list of :class:`WorkflowStep` instances consumed by :class:`WorkflowRunner`.
These tests verify:

    * Pre-refactor parity: each built-in :class:`WorkflowConfig` resolves to
      the same step counts and orderings the legacy ``get_*_pipeline`` helpers
      produced.
    * Conditional gating via :class:`StepCondition` against
      ``DEV_SEC_OPS_PLATFORM``.
    * Unknown slugs raise :class:`ValueError`.
    * The resolved steps carry ``step_id`` set to the invocation id.
    * The three plan slugs (``thin-plan``, ``patch-plan``, ``claude-code-plan``)
      resolve to :class:`PromptJsonStep` instances rather than the legacy
      concrete plan classes.
    * The ``implement-plan`` factory honours
      ``settings["plan_step_name"]``.
"""

import pytest

from rouge.core.workflow.config import StepInvocation, WorkflowConfig
from rouge.core.workflow.config_resolver import resolve_workflow
from rouge.core.workflow.executors.prompt_json_step import PromptJsonStep
from rouge.core.workflow.pipeline import (
    DIRECT_WORKFLOW_CONFIG,
    FULL_WORKFLOW_CONFIG,
    PATCH_WORKFLOW_CONFIG,
    THIN_WORKFLOW_CONFIG,
)
from rouge.core.workflow.steps import (
    CodeQualityStep,
    ComposeRequestStep,
    FetchIssueStep,
    FetchPatchStep,
    GitBranchStep,
    GitCheckoutStep,
    GitPrepareStep,
    ImplementPlanStep,
)
from rouge.core.workflow.steps.compose_commits_step import ComposeCommitsStep
from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep
from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep
from rouge.core.workflow.steps.implement_direct_step import ImplementDirectStep

# ---------------------------------------------------------------------------
# Built-in workflow parity
# ---------------------------------------------------------------------------


class TestResolveBuiltInWorkflows:
    """Built-in workflow configs resolve to the expected step shapes."""

    def test_full_workflow_no_platform(self, monkeypatch) -> None:
        """FULL config resolves to 6 steps with no PR step when platform unset."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        steps = resolve_workflow(FULL_WORKFLOW_CONFIG)

        assert len(steps) == 6

        # claude-code-plan is now a PromptJsonStep, not the legacy class.
        assert isinstance(steps[0], FetchIssueStep)
        assert isinstance(steps[1], GitBranchStep)
        assert isinstance(steps[2], PromptJsonStep)
        assert isinstance(steps[3], ImplementPlanStep)
        assert isinstance(steps[4], CodeQualityStep)
        assert isinstance(steps[5], ComposeRequestStep)

        # step_id is tagged from the invocation id for every step.
        assert [s.step_id for s in steps] == [
            "fetch-issue",
            "git-branch",
            "claude-code-plan",
            "implement-plan",
            "code-quality",
            "compose-request",
        ]

    def test_thin_workflow_no_platform(self, monkeypatch) -> None:
        """THIN config resolves to 5 steps with no PR step when platform unset."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        steps = resolve_workflow(THIN_WORKFLOW_CONFIG)

        assert len(steps) == 5
        assert isinstance(steps[0], FetchIssueStep)
        assert isinstance(steps[1], GitBranchStep)
        assert isinstance(steps[2], PromptJsonStep)
        assert isinstance(steps[3], ImplementPlanStep)
        assert isinstance(steps[4], ComposeRequestStep)

        assert [s.step_id for s in steps] == [
            "fetch-issue",
            "git-branch",
            "thin-plan",
            "implement-plan",
            "compose-request",
        ]

    def test_patch_workflow_no_platform(self, monkeypatch) -> None:
        """PATCH config resolves to 6 steps; PR steps never participate in patch."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        steps = resolve_workflow(PATCH_WORKFLOW_CONFIG)

        assert len(steps) == 6
        assert isinstance(steps[0], FetchPatchStep)
        assert isinstance(steps[1], GitCheckoutStep)
        assert isinstance(steps[2], PromptJsonStep)
        assert isinstance(steps[3], ImplementPlanStep)
        assert isinstance(steps[4], CodeQualityStep)
        assert isinstance(steps[5], ComposeCommitsStep)

        assert [s.step_id for s in steps] == [
            "fetch-patch",
            "git-checkout",
            "patch-plan",
            "implement-plan",
            "code-quality",
            "compose-commits",
        ]

    def test_direct_workflow(self, monkeypatch) -> None:
        """DIRECT config resolves to 3 steps without any plan/PR steps."""
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        steps = resolve_workflow(DIRECT_WORKFLOW_CONFIG)

        assert len(steps) == 3
        assert isinstance(steps[0], FetchIssueStep)
        assert isinstance(steps[1], GitPrepareStep)
        assert isinstance(steps[2], ImplementDirectStep)

        assert [s.step_id for s in steps] == [
            "fetch-issue",
            "git-prepare",
            "implement-direct",
        ]


# ---------------------------------------------------------------------------
# StepCondition gating
# ---------------------------------------------------------------------------


class TestPlatformGating:
    """``DEV_SEC_OPS_PLATFORM`` controls inclusion of PR/MR steps via when."""

    def test_full_workflow_github_includes_gh_pr(self, monkeypatch) -> None:
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        steps = resolve_workflow(FULL_WORKFLOW_CONFIG)

        assert len(steps) == 7
        assert isinstance(steps[-1], GhPullRequestStep)
        assert not any(isinstance(s, GlabPullRequestStep) for s in steps)

    def test_full_workflow_gitlab_includes_glab_mr(self, monkeypatch) -> None:
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        steps = resolve_workflow(FULL_WORKFLOW_CONFIG)

        assert len(steps) == 7
        assert isinstance(steps[-1], GlabPullRequestStep)
        assert not any(isinstance(s, GhPullRequestStep) for s in steps)

    def test_full_workflow_unset_excludes_pr(self, monkeypatch) -> None:
        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        steps = resolve_workflow(FULL_WORKFLOW_CONFIG)

        assert len(steps) == 6
        for step in steps:
            assert not isinstance(step, (GhPullRequestStep, GlabPullRequestStep))

    def test_full_workflow_unsupported_platform_excludes_pr(self, monkeypatch) -> None:
        """A platform value the configs don't match (e.g. bitbucket) excludes both."""
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "bitbucket")
        steps = resolve_workflow(FULL_WORKFLOW_CONFIG)

        assert len(steps) == 6
        for step in steps:
            assert not isinstance(step, (GhPullRequestStep, GlabPullRequestStep))

    def test_thin_workflow_github_includes_gh_pr(self, monkeypatch) -> None:
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        steps = resolve_workflow(THIN_WORKFLOW_CONFIG)

        assert len(steps) == 6
        assert isinstance(steps[-1], GhPullRequestStep)

    def test_thin_workflow_gitlab_includes_glab_mr(self, monkeypatch) -> None:
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        steps = resolve_workflow(THIN_WORKFLOW_CONFIG)

        assert len(steps) == 6
        assert isinstance(steps[-1], GlabPullRequestStep)


# ---------------------------------------------------------------------------
# Errors and step_id propagation
# ---------------------------------------------------------------------------


class TestResolverErrors:
    """Resolver fails fast for unknown slugs."""

    def test_unknown_slug_raises_value_error(self) -> None:
        config = WorkflowConfig(
            type_id="custom",
            steps=[StepInvocation(id="not-a-real-slug")],
        )
        with pytest.raises(ValueError, match="not-a-real-slug"):
            resolve_workflow(config)


class TestStepIdTagging:
    """Every resolved step has ``step_id`` set to the invocation id."""

    def test_step_id_set_on_every_step(self, monkeypatch) -> None:
        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        steps = resolve_workflow(FULL_WORKFLOW_CONFIG)

        # All step_ids must be non-empty strings matching the config.
        expected_ids = [
            "fetch-issue",
            "git-branch",
            "claude-code-plan",
            "implement-plan",
            "code-quality",
            "compose-request",
            "gh-pull-request",
        ]
        assert [s.step_id for s in steps] == expected_ids


# ---------------------------------------------------------------------------
# Plan slug overrides and implement-plan settings
# ---------------------------------------------------------------------------


class TestPlanSlugOverride:
    """Each legacy plan slug resolves to a :class:`PromptJsonStep` instance."""

    def test_claude_code_plan_resolves_to_prompt_json_step(self) -> None:
        config = WorkflowConfig(
            type_id="x",
            steps=[StepInvocation(id="claude-code-plan")],
        )
        steps = resolve_workflow(config)
        assert len(steps) == 1
        assert isinstance(steps[0], PromptJsonStep)
        # Default settings reflect the claude-code-plan slug.
        assert steps[0].settings.json_schema_kind == "plan_task"
        assert steps[0].settings.input_artifact == "fetch-issue"
        assert steps[0].settings.input_field == "issue"

    def test_thin_plan_resolves_to_prompt_json_step(self) -> None:
        config = WorkflowConfig(
            type_id="x",
            steps=[StepInvocation(id="thin-plan")],
        )
        steps = resolve_workflow(config)
        assert len(steps) == 1
        assert isinstance(steps[0], PromptJsonStep)
        assert steps[0].settings.json_schema_kind == "plan_chore_bug_feature"
        assert steps[0].settings.input_artifact == "fetch-issue"
        assert steps[0].settings.input_field == "issue"

    def test_patch_plan_resolves_to_prompt_json_step(self) -> None:
        config = WorkflowConfig(
            type_id="x",
            steps=[StepInvocation(id="patch-plan")],
        )
        steps = resolve_workflow(config)
        assert len(steps) == 1
        assert isinstance(steps[0], PromptJsonStep)
        assert steps[0].settings.json_schema_kind == "plan_chore_bug_feature"
        assert steps[0].settings.input_artifact == "fetch-patch"
        assert steps[0].settings.input_field == "patch"


class TestImplementPlanFactory:
    """``implement-plan`` honours ``settings['plan_step_name']``."""

    def test_implement_plan_uses_settings_plan_step_name(self) -> None:
        config = WorkflowConfig(
            type_id="x",
            steps=[
                StepInvocation(
                    id="implement-plan",
                    settings={"plan_step_name": "Building patch plan"},
                )
            ],
        )
        steps = resolve_workflow(config)
        assert len(steps) == 1
        assert isinstance(steps[0], ImplementPlanStep)
        assert steps[0].plan_step_name == "Building patch plan"

    def test_implement_plan_without_settings(self) -> None:
        """When no settings provided, ImplementPlanStep applies its default name."""
        config = WorkflowConfig(
            type_id="x",
            steps=[StepInvocation(id="implement-plan")],
        )
        steps = resolve_workflow(config)
        assert len(steps) == 1
        assert isinstance(steps[0], ImplementPlanStep)
        # ImplementPlanStep falls back to a generic default when no
        # plan_step_name is supplied.
        assert steps[0].plan_step_name == "Building implementation plan"

    def test_implement_plan_rejects_non_string_plan_step_name(self) -> None:
        config = WorkflowConfig(
            type_id="x",
            steps=[
                StepInvocation(
                    id="implement-plan",
                    settings={"plan_step_name": 42},
                )
            ],
        )
        with pytest.raises(ValueError, match="plan_step_name"):
            resolve_workflow(config)
