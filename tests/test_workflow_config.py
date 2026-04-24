"""Unit tests for declarative workflow configuration models."""

from typing import Any

import pytest
from pydantic import ValidationError

from rouge.core.prompts import PromptId
from rouge.core.workflow.config import (
    ArtifactBindingConfig,
    LegacyStepConfig,
    PromptJsonStepConfig,
    WorkflowConfig,
)


def _valid_prompt_step_data(**overrides: Any) -> dict[str, Any]:
    """Return a baseline valid PromptJsonStepConfig payload, with overrides applied."""
    base: dict[str, Any] = {
        "kind": "prompt-json",
        "step_id": "plan-step",
        "display_name": "Plan Step",
        "prompt_id": PromptId.CLAUDE_CODE_PLAN.value,
        "agent_name": "planner",
        "json_schema": "plan_schema",
        "required_fields": {"plan": "str", "tasks": "list"},
        "issue_binding": "fetch-issue",
        "output_artifact": "plan",
    }
    base.update(overrides)
    return base


def _valid_legacy_step_data(**overrides: Any) -> dict[str, Any]:
    """Return a baseline valid LegacyStepConfig payload, with overrides applied."""
    base: dict[str, Any] = {
        "kind": "legacy",
        "step_id": "git-branch",
        "display_name": "Git Branch",
        "import_path": "rouge.core.workflow.steps.git_branch_step:GitBranchStep",
    }
    base.update(overrides)
    return base


class TestArtifactBindingConfig:
    """Tests for ArtifactBindingConfig schema validation."""

    def test_valid_binding(self) -> None:
        """A valid artifact type and non-empty context_key are accepted."""
        binding = ArtifactBindingConfig(
            context_key="issue",
            artifact_type="fetch-issue",
        )
        assert binding.context_key == "issue"
        assert binding.artifact_type == "fetch-issue"
        assert binding.required is True

    def test_required_defaults_true(self) -> None:
        """The ``required`` field defaults to True."""
        binding = ArtifactBindingConfig(
            context_key="plan",
            artifact_type="plan",
        )
        assert binding.required is True

    def test_required_can_be_false(self) -> None:
        """Explicit ``required=False`` is preserved."""
        binding = ArtifactBindingConfig(
            context_key="plan",
            artifact_type="plan",
            required=False,
        )
        assert binding.required is False

    def test_unknown_artifact_type_raises(self) -> None:
        """An artifact_type not in ARTIFACT_MODELS fails validation."""
        with pytest.raises(ValidationError):
            ArtifactBindingConfig(
                context_key="issue",
                artifact_type="not-a-real-artifact",  # type: ignore[arg-type]
            )

    def test_empty_context_key_raises(self) -> None:
        """An empty or whitespace-only context_key fails validation."""
        with pytest.raises(ValidationError):
            ArtifactBindingConfig(
                context_key="",
                artifact_type="fetch-issue",
            )
        with pytest.raises(ValidationError):
            ArtifactBindingConfig(
                context_key="   ",
                artifact_type="fetch-issue",
            )


class TestPromptJsonStepConfig:
    """Tests for PromptJsonStepConfig schema validation."""

    def test_valid_prompt_step(self) -> None:
        """A fully-populated valid payload constructs successfully."""
        step = PromptJsonStepConfig(**_valid_prompt_step_data())
        assert step.kind == "prompt-json"
        assert step.step_id == "plan-step"
        assert step.model == "sonnet"
        assert step.prompt_id == PromptId.CLAUDE_CODE_PLAN
        assert step.output_artifact == "plan"
        assert step.rerun_target is None

    def test_prompt_id_accepts_enum_value(self) -> None:
        """String values of the PromptId enum are accepted."""
        step = PromptJsonStepConfig(**_valid_prompt_step_data(prompt_id=PromptId.THIN_PLAN.value))
        assert step.prompt_id == PromptId.THIN_PLAN

    def test_prompt_id_accepts_enum_instance(self) -> None:
        """PromptId enum instances are accepted directly."""
        step = PromptJsonStepConfig(**_valid_prompt_step_data(prompt_id=PromptId.PATCH_PLAN))
        assert step.prompt_id == PromptId.PATCH_PLAN

    def test_invalid_prompt_id_raises(self) -> None:
        """An unknown prompt_id value fails validation."""
        with pytest.raises(ValidationError):
            PromptJsonStepConfig(**_valid_prompt_step_data(prompt_id="no-such-prompt"))

    def test_required_fields_allowed_types(self) -> None:
        """All six allowed type names pass validation."""
        step = PromptJsonStepConfig(
            **_valid_prompt_step_data(
                required_fields={
                    "a": "str",
                    "b": "list",
                    "c": "dict",
                    "d": "int",
                    "e": "float",
                    "f": "bool",
                }
            )
        )
        assert step.required_fields["a"] == "str"
        assert step.required_fields["f"] == "bool"

    def test_required_fields_disallowed_type_raises(self) -> None:
        """A type name outside the allowed set fails validation."""
        with pytest.raises(ValidationError):
            PromptJsonStepConfig(**_valid_prompt_step_data(required_fields={"a": "tuple"}))

    def test_invalid_issue_binding_raises(self) -> None:
        """Only ``fetch-issue`` and ``fetch-patch`` are allowed for issue_binding."""
        with pytest.raises(ValidationError):
            PromptJsonStepConfig(**_valid_prompt_step_data(issue_binding="fetch-other"))

    def test_invalid_output_artifact_raises(self) -> None:
        """An unknown output_artifact value fails validation."""
        with pytest.raises(ValidationError):
            PromptJsonStepConfig(**_valid_prompt_step_data(output_artifact="not-an-artifact"))

    def test_rerun_target_accepts_kebab_case(self) -> None:
        """A kebab-case rerun_target slug is preserved."""
        step = PromptJsonStepConfig(**_valid_prompt_step_data(rerun_target="fetch-issue"))
        assert step.rerun_target == "fetch-issue"

    def test_rerun_target_rejects_invalid_slug(self) -> None:
        """A non-kebab-case rerun_target fails validation."""
        with pytest.raises(ValidationError):
            PromptJsonStepConfig(**_valid_prompt_step_data(rerun_target="Bad_Slug"))


class TestLegacyStepConfig:
    """Tests for LegacyStepConfig schema validation."""

    def test_valid_legacy_step(self) -> None:
        """A valid import_path and step metadata construct successfully."""
        step = LegacyStepConfig(**_valid_legacy_step_data())
        assert step.kind == "legacy"
        assert step.step_id == "git-branch"
        assert step.import_path == "rouge.core.workflow.steps.git_branch_step:GitBranchStep"
        assert step.init_kwargs == {}

    def test_init_kwargs_preserved(self) -> None:
        """Arbitrary init_kwargs payloads are preserved verbatim."""
        step = LegacyStepConfig(
            **_valid_legacy_step_data(init_kwargs={"retries": 3, "mode": "strict"})
        )
        assert step.init_kwargs == {"retries": 3, "mode": "strict"}

    def test_import_path_missing_colon_raises(self) -> None:
        """An import_path without exactly one colon fails validation."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(
                **_valid_legacy_step_data(
                    import_path="rouge.core.workflow.steps.git_branch_step.GitBranchStep"
                )
            )

    def test_import_path_multiple_colons_raises(self) -> None:
        """An import_path with more than one colon fails validation."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(import_path="pkg.mod:Cls:Extra"))

    def test_import_path_empty_raises(self) -> None:
        """An empty import_path fails validation."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(import_path=""))

    def test_import_path_invalid_identifier_raises(self) -> None:
        """An import_path with invalid module/class identifiers fails validation."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(import_path="pkg.mod:1Bad"))


class TestStepIdValidation:
    """Tests for kebab-case step_id regex enforcement."""

    def test_step_id_accepts_kebab_case(self) -> None:
        """Well-formed kebab-case slugs pass validation."""
        step = LegacyStepConfig(**_valid_legacy_step_data(step_id="my-step"))
        assert step.step_id == "my-step"

    def test_step_id_accepts_single_letter(self) -> None:
        """A single lowercase letter is a valid slug."""
        step = LegacyStepConfig(**_valid_legacy_step_data(step_id="a"))
        assert step.step_id == "a"

    def test_step_id_rejects_underscores_and_mixed_case(self) -> None:
        """``My_Step`` is rejected (uppercase + underscore)."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(step_id="My_Step"))

    def test_step_id_rejects_empty(self) -> None:
        """An empty step_id is rejected."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(step_id=""))

    def test_step_id_rejects_leading_digit(self) -> None:
        """A step_id starting with a digit is rejected."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(step_id="1step"))

    def test_step_id_rejects_leading_hyphen(self) -> None:
        """A step_id starting with a hyphen is rejected."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(step_id="-step"))


class TestOutputsValidation:
    """Tests for outputs list validation on ExecutorConfigBase."""

    def test_outputs_accepts_known_types(self) -> None:
        """Outputs referencing known artifact types are accepted."""
        step = LegacyStepConfig(**_valid_legacy_step_data(outputs=["git-branch", "fetch-issue"]))
        assert step.outputs == ["git-branch", "fetch-issue"]

    def test_outputs_rejects_unknown_type(self) -> None:
        """Outputs referencing unknown artifact types are rejected."""
        with pytest.raises(ValidationError):
            LegacyStepConfig(**_valid_legacy_step_data(outputs=["totally-fake"]))


class TestDiscriminatedUnion:
    """Tests for StepInvocationConfig discriminated union parsing."""

    def test_prompt_json_kind_parses_to_prompt_json_config(self) -> None:
        """A dict with kind=prompt-json parses to PromptJsonStepConfig."""
        workflow = WorkflowConfig(
            type_id="test",
            steps=[_valid_prompt_step_data()],
        )
        assert isinstance(workflow.steps[0], PromptJsonStepConfig)

    def test_legacy_kind_parses_to_legacy_config(self) -> None:
        """A dict with kind=legacy parses to LegacyStepConfig."""
        workflow = WorkflowConfig(
            type_id="test",
            steps=[_valid_legacy_step_data()],
        )
        assert isinstance(workflow.steps[0], LegacyStepConfig)

    def test_unknown_kind_raises(self) -> None:
        """A dict with an unknown kind value fails validation."""
        bad_step = dict(_valid_legacy_step_data())
        bad_step["kind"] = "not-a-kind"
        with pytest.raises(ValidationError):
            WorkflowConfig(type_id="test", steps=[bad_step])

    def test_missing_kind_raises(self) -> None:
        """A dict missing the discriminator field fails validation."""
        bad_step = dict(_valid_legacy_step_data())
        del bad_step["kind"]
        with pytest.raises(ValidationError):
            WorkflowConfig(type_id="test", steps=[bad_step])

    def test_mixed_kinds_in_single_workflow(self) -> None:
        """A workflow may mix prompt-json and legacy steps."""
        workflow = WorkflowConfig(
            type_id="test",
            steps=[
                _valid_legacy_step_data(),
                _valid_prompt_step_data(),
            ],
        )
        assert isinstance(workflow.steps[0], LegacyStepConfig)
        assert isinstance(workflow.steps[1], PromptJsonStepConfig)


class TestWorkflowConfig:
    """Tests for WorkflowConfig-level validators."""

    def test_valid_workflow(self) -> None:
        """A minimal valid workflow constructs successfully."""
        workflow = WorkflowConfig(
            type_id="full",
            description="Full pipeline",
            steps=[_valid_legacy_step_data()],
        )
        assert workflow.type_id == "full"
        assert workflow.description == "Full pipeline"
        assert len(workflow.steps) == 1

    def test_empty_type_id_raises(self) -> None:
        """An empty type_id is rejected."""
        with pytest.raises(ValidationError):
            WorkflowConfig(type_id="", steps=[_valid_legacy_step_data()])

    def test_duplicate_step_ids_raise(self) -> None:
        """Duplicate step_id values across steps are rejected."""
        with pytest.raises(ValidationError) as exc_info:
            WorkflowConfig(
                type_id="test",
                steps=[
                    _valid_legacy_step_data(step_id="shared"),
                    _valid_legacy_step_data(step_id="shared"),
                ],
            )
        assert "Duplicate" in str(exc_info.value) or "duplicate" in str(exc_info.value)

    def test_platform_gate_accepts_known_slugs(self) -> None:
        """platform_gate entries referencing existing step slugs are accepted."""
        workflow = WorkflowConfig(
            type_id="test",
            steps=[
                _valid_legacy_step_data(
                    step_id="gh-pull-request",
                    import_path="rouge.pkg.mod:GhStep",
                ),
                _valid_legacy_step_data(
                    step_id="glab-pull-request",
                    import_path="rouge.pkg.mod:GlabStep",
                ),
            ],
            platform_gate={
                "github": ["gh-pull-request"],
                "gitlab": ["glab-pull-request"],
            },
        )
        assert workflow.platform_gate is not None
        assert workflow.platform_gate["github"] == ["gh-pull-request"]

    def test_platform_gate_unknown_slug_raises(self) -> None:
        """platform_gate referencing a slug not in steps is rejected."""
        with pytest.raises(ValidationError) as exc_info:
            WorkflowConfig(
                type_id="test",
                steps=[_valid_legacy_step_data(step_id="gh-pull-request")],
                platform_gate={"gitlab": ["glab-pull-request"]},
            )
        assert "unknown step slugs" in str(exc_info.value)

    def test_platform_gate_none_is_allowed(self) -> None:
        """platform_gate=None is a valid default."""
        workflow = WorkflowConfig(
            type_id="test",
            steps=[_valid_legacy_step_data()],
        )
        assert workflow.platform_gate is None


class TestRoundTrip:
    """Tests that model_dump/model_validate preserve all data."""

    def test_round_trip_preserves_prompt_step(self) -> None:
        """A WorkflowConfig containing a PromptJsonStepConfig round-trips losslessly."""
        original = WorkflowConfig(
            type_id="full",
            description="Full pipeline",
            steps=[
                _valid_prompt_step_data(
                    step_id="plan-step",
                    rerun_target="fetch-issue",
                    inputs=[
                        {
                            "context_key": "issue",
                            "artifact_type": "fetch-issue",
                            "required": True,
                        }
                    ],
                    outputs=["plan"],
                ),
            ],
        )
        dumped = original.model_dump()
        restored = WorkflowConfig.model_validate(dumped)

        assert restored.model_dump() == dumped
        assert isinstance(restored.steps[0], PromptJsonStepConfig)
        assert restored.steps[0].rerun_target == "fetch-issue"
        assert restored.steps[0].inputs[0].artifact_type == "fetch-issue"

    def test_round_trip_preserves_legacy_step(self) -> None:
        """A WorkflowConfig containing a LegacyStepConfig round-trips losslessly."""
        original = WorkflowConfig(
            type_id="patch",
            steps=[
                _valid_legacy_step_data(
                    init_kwargs={"mode": "strict"},
                    outputs=["git-branch"],
                    inputs=[
                        {
                            "context_key": "issue",
                            "artifact_type": "fetch-issue",
                            "required": False,
                        }
                    ],
                ),
            ],
        )
        dumped = original.model_dump()
        restored = WorkflowConfig.model_validate(dumped)

        assert restored.model_dump() == dumped
        assert isinstance(restored.steps[0], LegacyStepConfig)
        assert restored.steps[0].init_kwargs == {"mode": "strict"}

    def test_round_trip_with_platform_gate(self) -> None:
        """platform_gate survives a model_dump/model_validate cycle."""
        original = WorkflowConfig(
            type_id="test",
            steps=[
                _valid_legacy_step_data(
                    step_id="gh-pull-request",
                    import_path="pkg.mod:A",
                ),
                _valid_legacy_step_data(
                    step_id="glab-pull-request",
                    import_path="pkg.mod:B",
                ),
            ],
            platform_gate={
                "github": ["gh-pull-request"],
                "gitlab": ["glab-pull-request"],
            },
        )
        dumped = original.model_dump()
        restored = WorkflowConfig.model_validate(dumped)

        assert restored.model_dump() == dumped
        assert restored.platform_gate == {
            "github": ["gh-pull-request"],
            "gitlab": ["glab-pull-request"],
        }

    def test_round_trip_mixed_kinds(self) -> None:
        """A workflow with mixed step kinds round-trips losslessly."""
        original = WorkflowConfig(
            type_id="mixed",
            steps=[
                _valid_legacy_step_data(step_id="leg", import_path="pkg.mod:A"),
                _valid_prompt_step_data(step_id="prm"),
            ],
        )
        dumped = original.model_dump()
        restored = WorkflowConfig.model_validate(dumped)

        assert restored.model_dump() == dumped
        assert isinstance(restored.steps[0], LegacyStepConfig)
        assert isinstance(restored.steps[1], PromptJsonStepConfig)
