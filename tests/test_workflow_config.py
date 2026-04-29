"""Unit tests for declarative workflow config models.

These tests cover the validators on :class:`StepInvocation`,
:class:`StepCondition`, and :class:`WorkflowConfig` so that misconfiguration
fails fast at construction time rather than at workflow-resolution time.

The models live in :mod:`rouge.core.workflow.config`; see the module docstring
there for the high-level intent of each model.
"""

import pytest
from pydantic import ValidationError

from rouge.core.workflow.config import StepCondition, StepInvocation, WorkflowConfig


class TestStepInvocationValidators:
    """Validators on :class:`StepInvocation`."""

    def test_rejects_empty_id(self) -> None:
        """An empty id must be rejected."""
        with pytest.raises(ValidationError):
            StepInvocation(id="")

    def test_rejects_whitespace_only_id(self) -> None:
        """An id that becomes empty after .strip() must be rejected."""
        with pytest.raises(ValidationError):
            StepInvocation(id="   ")

    def test_trims_id_whitespace(self) -> None:
        """Surrounding whitespace on a non-empty id is trimmed."""
        invocation = StepInvocation(id="  fetch-issue  ")
        assert invocation.id == "fetch-issue"

    def test_display_name_trimmed_to_none_when_blank(self) -> None:
        """Whitespace-only display_name is normalized to None."""
        invocation = StepInvocation(id="fetch-issue", display_name="   ")
        assert invocation.display_name is None

    def test_display_name_preserved_when_set(self) -> None:
        """Non-empty display_name is preserved (and trimmed)."""
        invocation = StepInvocation(id="fetch-issue", display_name="  Hello  ")
        assert invocation.display_name == "Hello"


class TestStepConditionValidators:
    """Validators and accepted shapes on :class:`StepCondition`."""

    def test_env_only_means_set_and_non_empty(self) -> None:
        """``env`` alone (no equals/in) is a valid 'is set' condition."""
        cond = StepCondition(env="DEV_SEC_OPS_PLATFORM")
        assert cond.env == "DEV_SEC_OPS_PLATFORM"
        assert cond.equals is None
        assert cond.in_ is None

    def test_env_with_equals(self) -> None:
        """``env`` + ``equals`` is accepted."""
        cond = StepCondition(env="DEV_SEC_OPS_PLATFORM", equals="github")
        assert cond.env == "DEV_SEC_OPS_PLATFORM"
        assert cond.equals == "github"
        assert cond.in_ is None

    def test_env_with_in_alias(self) -> None:
        """The YAML-friendly ``in`` alias populates ``in_``."""
        cond = StepCondition.model_validate(
            {"env": "DEV_SEC_OPS_PLATFORM", "in": ["github", "gitlab"]}
        )
        assert cond.in_ == ["github", "gitlab"]

    def test_env_with_in_python_attribute(self) -> None:
        """The Python attribute name ``in_`` also populates the field."""
        cond = StepCondition(env="DEV_SEC_OPS_PLATFORM", in_=["github", "gitlab"])
        assert cond.in_ == ["github", "gitlab"]

    def test_rejects_empty_env(self) -> None:
        """An empty env name must be rejected."""
        with pytest.raises(ValidationError):
            StepCondition(env="")

    def test_rejects_whitespace_only_env(self) -> None:
        """An env that becomes empty after strip must be rejected."""
        with pytest.raises(ValidationError):
            StepCondition(env="   ")

    def test_trims_env_whitespace(self) -> None:
        """Surrounding whitespace on a non-empty env is trimmed."""
        cond = StepCondition(env="  DEV_SEC_OPS_PLATFORM  ")
        assert cond.env == "DEV_SEC_OPS_PLATFORM"


class TestWorkflowConfigValidators:
    """Validators on :class:`WorkflowConfig`."""

    def test_rejects_empty_steps(self) -> None:
        """An empty step list is rejected."""
        with pytest.raises(ValidationError):
            WorkflowConfig(type_id="full", steps=[])

    def test_rejects_empty_type_id(self) -> None:
        """An empty type_id is rejected."""
        with pytest.raises(ValidationError):
            WorkflowConfig(type_id="", steps=[StepInvocation(id="fetch-issue")])

    def test_rejects_whitespace_only_type_id(self) -> None:
        """A type_id that becomes empty after strip is rejected."""
        with pytest.raises(ValidationError):
            WorkflowConfig(type_id="   ", steps=[StepInvocation(id="fetch-issue")])

    def test_trims_type_id(self) -> None:
        """Surrounding whitespace on a non-empty type_id is trimmed."""
        config = WorkflowConfig(type_id="  full  ", steps=[StepInvocation(id="fetch-issue")])
        assert config.type_id == "full"

    def test_rejects_duplicate_step_ids(self) -> None:
        """Two invocations sharing the same id must be rejected."""
        with pytest.raises(ValidationError) as excinfo:
            WorkflowConfig(
                type_id="full",
                steps=[
                    StepInvocation(id="fetch-issue"),
                    StepInvocation(id="git-branch"),
                    StepInvocation(id="fetch-issue"),
                ],
            )
        assert "duplicate step id" in str(excinfo.value)

    def test_accepts_unique_step_ids(self) -> None:
        """A workflow with unique step ids is accepted."""
        config = WorkflowConfig(
            type_id="full",
            steps=[
                StepInvocation(id="fetch-issue"),
                StepInvocation(id="git-branch"),
            ],
        )
        assert len(config.steps) == 2
        assert config.steps[0].id == "fetch-issue"
        assert config.steps[1].id == "git-branch"
