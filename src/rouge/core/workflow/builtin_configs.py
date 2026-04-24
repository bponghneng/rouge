"""Declarative :class:`WorkflowConfig` constants for the built-in pipelines.

This module centralises the configuration that previously lived inside the
hand-coded ``get_full_pipeline``/``get_thin_pipeline``/``get_patch_pipeline``/
``get_direct_pipeline`` functions in :mod:`rouge.core.workflow.pipeline`.

Each :data:`WorkflowConfig` constant below enumerates the same step sequence
as the corresponding legacy builder function.  Plan steps are expressed as
:class:`PromptJsonStepConfig` entries so the reusable
:class:`~rouge.core.workflow.executors.prompt_json_step.PromptJsonStep`
executor can drive them; all other steps are wrapped as
:class:`LegacyStepConfig` entries that import and instantiate their legacy
:class:`~rouge.core.workflow.step_base.WorkflowStep` classes.

The :class:`CLAUDE_CODE_PLAN_CONFIG`, :class:`THIN_PLAN_CONFIG`, and
:class:`PATCH_PLAN_CONFIG` constants are also exported individually so the
shim classes in ``rouge.core.workflow.steps.claude_code_plan_step``,
``thin_plan_step``, and ``patch_plan_step`` can default-construct a
:class:`PromptJsonStep` with zero arguments, preserving back-compat for the
legacy plan-step tests that construct these classes directly.
"""

from __future__ import annotations

from rouge.core.prompts import PromptId
from rouge.core.workflow.config import (
    LegacyStepConfig,
    PromptJsonStepConfig,
    WorkflowConfig,
)
from rouge.core.workflow.shared import AGENT_PLANNER

# ---------------------------------------------------------------------------
# Plan-step JSON schemas and required_fields maps
# ---------------------------------------------------------------------------

# Task-keyed schema used by the full-workflow ClaudeCodePlanStep prompt.
_CLAUDE_CODE_PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "task": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["task", "output", "plan", "summary"]
}"""

_CLAUDE_CODE_PLAN_REQUIRED_FIELDS: dict[str, str] = {
    "task": "str",
    "output": "str",
    "plan": "str",
    "summary": "str",
}

# Type-keyed schema shared by the thin-plan and patch-plan prompts.
_TYPE_KEYED_PLAN_JSON_SCHEMA = """{
  "type": "object",
  "properties": {
    "type": { "type": "string", "minLength": 1 },
    "output": { "type": "string", "const": "plan" },
    "plan": { "type": "string", "minLength": 1 },
    "summary": { "type": "string", "minLength": 1 }
  },
  "required": ["type", "output", "plan", "summary"]
}"""

_TYPE_KEYED_PLAN_REQUIRED_FIELDS: dict[str, str] = {
    "type": "str",
    "output": "str",
    "plan": "str",
    "summary": "str",
}


# ---------------------------------------------------------------------------
# Plan step configs (exported for shim classes)
# ---------------------------------------------------------------------------

CLAUDE_CODE_PLAN_CONFIG = PromptJsonStepConfig(
    step_id="claude-code-plan",
    display_name="Building task-oriented implementation plan",
    prompt_id=PromptId.CLAUDE_CODE_PLAN,
    agent_name=AGENT_PLANNER,
    model="sonnet",
    json_schema=_CLAUDE_CODE_PLAN_JSON_SCHEMA,
    required_fields=_CLAUDE_CODE_PLAN_REQUIRED_FIELDS,
    issue_binding="fetch-issue",
    output_artifact="plan",
    critical=True,
    outputs=["plan"],
    inputs=[],
    rerun_target=None,
)

THIN_PLAN_CONFIG = PromptJsonStepConfig(
    step_id="thin-plan",
    display_name="Building thin implementation plan",
    prompt_id=PromptId.THIN_PLAN,
    agent_name=AGENT_PLANNER,
    model="sonnet",
    json_schema=_TYPE_KEYED_PLAN_JSON_SCHEMA,
    required_fields=_TYPE_KEYED_PLAN_REQUIRED_FIELDS,
    issue_binding="fetch-issue",
    output_artifact="plan",
    critical=True,
    outputs=["plan"],
    inputs=[],
    rerun_target=None,
)

PATCH_PLAN_CONFIG = PromptJsonStepConfig(
    step_id="patch-plan",
    display_name="Building patch plan",
    prompt_id=PromptId.PATCH_PLAN,
    agent_name=AGENT_PLANNER,
    model="sonnet",
    json_schema=_TYPE_KEYED_PLAN_JSON_SCHEMA,
    required_fields=_TYPE_KEYED_PLAN_REQUIRED_FIELDS,
    issue_binding="fetch-patch",
    output_artifact="plan",
    critical=True,
    outputs=["plan"],
    inputs=[],
    rerun_target=None,
)


# ---------------------------------------------------------------------------
# Legacy step configs
# ---------------------------------------------------------------------------

_FETCH_ISSUE_CONFIG = LegacyStepConfig(
    step_id="fetch-issue",
    display_name="Fetching issue",
    import_path="rouge.core.workflow.steps.fetch_issue_step:FetchIssueStep",
    critical=True,
    outputs=["fetch-issue"],
)

_FETCH_PATCH_CONFIG = LegacyStepConfig(
    step_id="fetch-patch",
    display_name="Fetching patch",
    import_path="rouge.core.workflow.steps.fetch_patch_step:FetchPatchStep",
    critical=True,
    outputs=["fetch-patch"],
)

_GIT_BRANCH_CONFIG = LegacyStepConfig(
    step_id="git-branch",
    display_name="Setting up git branch",
    import_path="rouge.core.workflow.steps.git_branch_step:GitBranchStep",
    critical=True,
    outputs=["git-branch"],
)

_GIT_CHECKOUT_CONFIG = LegacyStepConfig(
    step_id="git-checkout",
    display_name="Checking out git branch",
    import_path="rouge.core.workflow.steps.git_checkout_step:GitCheckoutStep",
    critical=True,
    outputs=["git-checkout"],
)

_GIT_PREPARE_CONFIG = LegacyStepConfig(
    step_id="git-prepare",
    display_name="Preparing git workspace",
    import_path="rouge.core.workflow.steps.git_prepare_step:GitPrepareStep",
    critical=True,
    outputs=["git-branch", "git-checkout"],
)

_CODE_QUALITY_CONFIG = LegacyStepConfig(
    step_id="code-quality",
    display_name="Running code quality checks",
    import_path="rouge.core.workflow.steps.code_quality_step:CodeQualityStep",
    critical=False,
    outputs=["code-quality"],
)

_COMPOSE_REQUEST_CONFIG = LegacyStepConfig(
    step_id="compose-request",
    display_name="Composing pull request metadata",
    import_path=("rouge.core.workflow.steps.compose_request_step:ComposeRequestStep"),
    critical=True,
    outputs=["compose-request"],
)

_COMPOSE_COMMITS_CONFIG = LegacyStepConfig(
    step_id="compose-commits",
    display_name="Pushing commits to existing PR/MR",
    import_path=("rouge.core.workflow.steps.compose_commits_step:ComposeCommitsStep"),
    critical=False,
    outputs=["compose-commits"],
)

_GH_PULL_REQUEST_CONFIG = LegacyStepConfig(
    step_id="gh-pull-request",
    display_name="Creating GitHub pull request",
    import_path=("rouge.core.workflow.steps.gh_pull_request_step:GhPullRequestStep"),
    critical=False,
    outputs=["gh-pull-request"],
)

_GLAB_PULL_REQUEST_CONFIG = LegacyStepConfig(
    step_id="glab-pull-request",
    display_name="Creating GitLab merge request",
    import_path=("rouge.core.workflow.steps.glab_pull_request_step:GlabPullRequestStep"),
    critical=False,
    outputs=["glab-pull-request"],
)

_IMPLEMENT_DIRECT_CONFIG = LegacyStepConfig(
    step_id="implement-direct",
    display_name="Implementing directly from issue",
    import_path=("rouge.core.workflow.steps.implement_direct_step:ImplementDirectStep"),
    critical=True,
    outputs=["implement:direct"],
)


def _implement_plan_config(plan_step_id: str) -> LegacyStepConfig:
    """Build an ImplementPlanStep ``LegacyStepConfig`` bound to *plan_step_id*."""
    return LegacyStepConfig(
        step_id="implement-plan",
        display_name="Implementing plan-based solution",
        import_path=("rouge.core.workflow.steps.implement_step:ImplementPlanStep"),
        critical=True,
        outputs=["implement"],
        init_kwargs={"plan_step_id": plan_step_id},
    )


# ---------------------------------------------------------------------------
# Built-in workflow configs
# ---------------------------------------------------------------------------

FULL_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="full",
    description="Full workflow pipeline with Claude Code planning",
    steps=[
        _FETCH_ISSUE_CONFIG,
        _GIT_BRANCH_CONFIG,
        CLAUDE_CODE_PLAN_CONFIG,
        _implement_plan_config("claude-code-plan"),
        _CODE_QUALITY_CONFIG,
        _COMPOSE_REQUEST_CONFIG,
        _GH_PULL_REQUEST_CONFIG,
        _GLAB_PULL_REQUEST_CONFIG,
    ],
    platform_gate={
        "github": ["gh-pull-request"],
        "gitlab": ["glab-pull-request"],
    },
)

THIN_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="thin",
    description="Thin workflow pipeline for straightforward issues",
    steps=[
        _FETCH_ISSUE_CONFIG,
        _GIT_BRANCH_CONFIG,
        THIN_PLAN_CONFIG,
        _implement_plan_config("thin-plan"),
        _COMPOSE_REQUEST_CONFIG,
        _GH_PULL_REQUEST_CONFIG,
        _GLAB_PULL_REQUEST_CONFIG,
    ],
    platform_gate={
        "github": ["gh-pull-request"],
        "gitlab": ["glab-pull-request"],
    },
)

PATCH_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="patch",
    description="Patch workflow pipeline",
    steps=[
        _FETCH_PATCH_CONFIG,
        _GIT_CHECKOUT_CONFIG,
        PATCH_PLAN_CONFIG,
        _implement_plan_config("patch-plan"),
        _CODE_QUALITY_CONFIG,
        _COMPOSE_COMMITS_CONFIG,
    ],
    platform_gate=None,
)

DIRECT_WORKFLOW_CONFIG = WorkflowConfig(
    type_id="direct",
    description=("Direct workflow — implements from issue description without planning"),
    steps=[
        _FETCH_ISSUE_CONFIG,
        _GIT_PREPARE_CONFIG,
        _IMPLEMENT_DIRECT_CONFIG,
    ],
    platform_gate=None,
)


__all__ = [
    "CLAUDE_CODE_PLAN_CONFIG",
    "DIRECT_WORKFLOW_CONFIG",
    "FULL_WORKFLOW_CONFIG",
    "PATCH_PLAN_CONFIG",
    "PATCH_WORKFLOW_CONFIG",
    "THIN_PLAN_CONFIG",
    "THIN_WORKFLOW_CONFIG",
]
