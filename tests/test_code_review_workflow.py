"""Tests for the codereview workflow: registry, pipeline, and loop behaviour.

Complements tests in test_adw.py (loop orchestration) and
test_workflow_registry.py (generic registry mechanics) by focusing on
codereview-specific registration, pipeline composition, and integration
between the registry and the loop.
"""

import pathlib
from typing import Generator

import pytest

from rouge.core.workflow.pipeline import get_code_review_pipeline
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.steps.code_quality_step import CodeQualityStep
from rouge.core.workflow.steps.code_review_step import CodeReviewStep
from rouge.core.workflow.steps.review_fix_step import ReviewFixStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_registry import (
    get_pipeline_for_type,
    get_workflow_registry,
    reset_workflow_registry,
)


@pytest.fixture(autouse=True)
def _reset_registry() -> Generator[None, None, None]:
    """Reset the global workflow registry before and after each test."""
    reset_workflow_registry()
    yield
    reset_workflow_registry()


# ---------------------------------------------------------------------------
# Registry registration tests
# ---------------------------------------------------------------------------


class TestCodeReviewRegistration:
    """Verify the codereview workflow is registered in the global registry."""

    def test_codereview_is_registered(self) -> None:
        """The default registry should contain a 'codereview' workflow type."""
        registry = get_workflow_registry()

        assert registry.is_registered("codereview")

    def test_codereview_in_list_types(self) -> None:
        """'codereview' should appear in the registry's list of available types."""
        registry = get_workflow_registry()
        types = registry.list_types()

        assert "codereview" in types

    def test_registry_pipeline_returns_workflow_steps(self) -> None:
        """get_pipeline via the registry should return a list of WorkflowStep instances."""
        registry = get_workflow_registry()
        pipeline = registry.get_pipeline("codereview")

        assert isinstance(pipeline, list)
        assert len(pipeline) > 0
        assert all(isinstance(step, WorkflowStep) for step in pipeline)


# ---------------------------------------------------------------------------
# Pipeline structure tests
# ---------------------------------------------------------------------------


class TestCodeReviewPipeline:
    """Verify the codereview pipeline contains the correct steps in order."""

    def test_pipeline_contains_three_steps(self) -> None:
        """The codereview pipeline should contain exactly 3 steps."""
        pipeline = get_code_review_pipeline()

        assert len(pipeline) == 3

    def test_pipeline_step_order(self) -> None:
        """Steps should be: CodeReviewStep, ReviewFixStep, CodeQualityStep."""
        pipeline = get_code_review_pipeline()

        expected_types = [
            CodeReviewStep,
            ReviewFixStep,
            CodeQualityStep,
        ]

        for i, (step, expected_type) in enumerate(zip(pipeline, expected_types, strict=True)):
            assert isinstance(
                step, expected_type
            ), f"Step {i} should be {expected_type.__name__}, got {type(step).__name__}"

    def test_pipeline_step_names(self) -> None:
        """Each step should expose the expected human-readable name."""
        pipeline = get_code_review_pipeline()

        assert pipeline[0].name == "Generating CodeRabbit review"
        assert pipeline[1].name == "Addressing review issues"
        # CodeQualityStep name - just verify it has one
        assert isinstance(pipeline[2].name, str)
        assert len(pipeline[2].name) > 0

    def test_all_steps_are_best_effort(self) -> None:
        """All steps in the codereview pipeline should be non-critical (best-effort).

        The review pipeline is used in a loop where individual step failures
        are tolerated; only the loop orchestrator decides whether to abort.
        """
        pipeline = get_code_review_pipeline()

        for step in pipeline:
            assert (
                not step.is_critical
            ), f"Step '{step.name}' should be best-effort (is_critical=False)"

    def test_pipeline_does_not_include_issue_dependent_steps(self) -> None:
        """Codereview pipeline should not contain steps that require an issue."""
        from rouge.core.workflow.steps import (
            AcceptanceStep,
            ClassifyStep,
            ComposeRequestStep,
            FetchIssueStep,
            GitSetupStep,
            ImplementStep,
            PlanStep,
        )

        issue_dependent_types = (
            GitSetupStep,
            FetchIssueStep,
            ClassifyStep,
            PlanStep,
            ImplementStep,
            AcceptanceStep,
            ComposeRequestStep,
        )

        pipeline = get_code_review_pipeline()

        for step in pipeline:
            assert not isinstance(
                step, issue_dependent_types
            ), f"Codereview pipeline should not contain {type(step).__name__}"


# ---------------------------------------------------------------------------
# get_pipeline_for_type integration tests
# ---------------------------------------------------------------------------


class TestGetPipelineForTypeCodeReview:
    """Verify get_pipeline_for_type resolves 'codereview' correctly."""

    def test_returns_codereview_pipeline(self) -> None:
        """get_pipeline_for_type('codereview') should resolve via registry."""
        pipeline = get_pipeline_for_type("codereview")

        assert isinstance(pipeline, list)
        assert len(pipeline) == 3
        assert all(isinstance(step, WorkflowStep) for step in pipeline)

    def test_pipeline_matches_direct_call(self) -> None:
        """Pipeline from get_pipeline_for_type should match get_code_review_pipeline."""
        from_helper = get_pipeline_for_type("codereview")
        from_direct = get_code_review_pipeline()

        assert len(from_helper) == len(from_direct)
        for h, d in zip(from_helper, from_direct):
            assert type(h) is type(d)


# ---------------------------------------------------------------------------
# Loop behaviour tests (complementary to test_adw.py)
# ---------------------------------------------------------------------------


class _FakeArtifactStore:
    """Minimal fake ArtifactStore for loop tests."""

    def __init__(self, workflow_id: str, base_path):
        self._workflow_id = workflow_id
        self.workflow_dir = base_path / workflow_id

    @property
    def workflow_id(self) -> str:
        return self._workflow_id


class _FakeStep(WorkflowStep):
    """Configurable fake step for loop tests."""

    def __init__(self, name: str, *, critical: bool = True, succeed: bool = True):
        self._name = name
        self._critical = critical
        self._succeed = succeed
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_critical(self) -> bool:
        return self._critical

    def run(self, context: WorkflowContext) -> StepResult:
        self.call_count += 1
        if self._succeed:
            return StepResult.ok(data=None)
        return StepResult.fail(error=f"{self._name} failed")


class _CleanOnIterationStep(WorkflowStep):
    """Step that sets review_is_clean after a specific number of calls."""

    def __init__(self, clean_on: int = 1):
        self._clean_on = clean_on
        self.call_count = 0

    @property
    def name(self) -> str:
        return "review-check"

    def run(self, context: WorkflowContext) -> StepResult:
        self.call_count += 1
        if self.call_count >= self._clean_on:
            context.data["review_is_clean"] = True
        return StepResult.ok(data=None)


def _patch_loop_deps(monkeypatch, tmp_path: pathlib.Path, pipeline) -> None:
    """Patch get_pipeline_for_type and ArtifactStore for loop tests."""
    monkeypatch.setattr("rouge.adw.adw.get_pipeline_for_type", lambda t: pipeline)
    monkeypatch.setattr(
        "rouge.adw.adw.ArtifactStore",
        lambda wid: _FakeArtifactStore(wid, tmp_path),
    )


class TestCodeReviewLoopBehaviour:
    """Loop behaviour tests complementary to test_adw.py.

    These tests focus on codereview-specific scenarios not covered by
    the generic loop tests in test_adw.py.
    """

    def test_loop_exits_on_clean_review_first_iteration(
        self, monkeypatch, tmp_path: pathlib.Path
    ) -> None:
        """Loop should succeed immediately when review is clean on first pass."""
        from rouge.adw.adw import execute_code_review_loop

        clean_step = _CleanOnIterationStep(clean_on=1)
        pipeline = [_FakeStep("generate"), clean_step, _FakeStep("quality")]
        _patch_loop_deps(monkeypatch, tmp_path, pipeline)

        success, wid = execute_code_review_loop(workflow_id="cr-clean-001")

        assert success is True
        assert wid == "cr-clean-001"
        assert clean_step.call_count == 1

    def test_loop_exits_after_max_iterations(self, monkeypatch, tmp_path: pathlib.Path) -> None:
        """Loop should fail when max iterations exhausted without clean review."""
        from rouge.adw.adw import execute_code_review_loop

        pipeline = [
            _FakeStep("generate"),
            _FakeStep("address"),
            _FakeStep("quality"),
        ]
        _patch_loop_deps(monkeypatch, tmp_path, pipeline)

        success, wid = execute_code_review_loop(workflow_id="cr-exhaust-001", max_iterations=2)

        assert success is False
        assert wid == "cr-exhaust-001"
        # Each step should have been called max_iterations times
        for step in pipeline:
            assert step.call_count == 2

    def test_critical_step_failure_aborts_loop(self, monkeypatch, tmp_path: pathlib.Path) -> None:
        """A critical step failure should abort the loop immediately."""
        from rouge.adw.adw import execute_code_review_loop

        failing = _FakeStep("generate", critical=True, succeed=False)
        address = _FakeStep("address")
        quality = _FakeStep("quality")
        pipeline = [failing, address, quality]
        _patch_loop_deps(monkeypatch, tmp_path, pipeline)

        success, wid = execute_code_review_loop(workflow_id="cr-abort-001")

        assert success is False
        assert wid == "cr-abort-001"
        assert failing.call_count == 1
        # Steps after the critical failure should not have been reached
        assert address.call_count == 0
        assert quality.call_count == 0

    def test_config_base_commit_passed_through_to_context(
        self, monkeypatch, tmp_path: pathlib.Path
    ) -> None:
        """The base_commit config value should be available in context.data."""
        from rouge.adw.adw import execute_code_review_loop

        captured = {}

        class _CaptureConfigStep(WorkflowStep):
            @property
            def name(self) -> str:
                return "capture"

            def run(self, context: WorkflowContext) -> StepResult:
                captured["base_commit"] = context.data.get("base_commit")
                captured["all_data"] = dict(context.data)
                context.data["review_is_clean"] = True
                return StepResult.ok(data=None)

        pipeline = [_CaptureConfigStep()]
        _patch_loop_deps(monkeypatch, tmp_path, pipeline)

        success, wid = execute_code_review_loop(
            workflow_id="cr-config-001",
            config={"base_commit": "abc123deadbeef"},
        )

        assert success is True
        assert captured["base_commit"] == "abc123deadbeef"

    def test_config_none_does_not_seed_context(self, monkeypatch, tmp_path: pathlib.Path) -> None:
        """When config is None, context.data should not contain base_commit."""
        from rouge.adw.adw import execute_code_review_loop

        captured = {}

        class _CaptureStep(WorkflowStep):
            @property
            def name(self) -> str:
                return "capture"

            def run(self, context: WorkflowContext) -> StepResult:
                captured["has_base_commit"] = "base_commit" in context.data
                context.data["review_is_clean"] = True
                return StepResult.ok(data=None)

        pipeline = [_CaptureStep()]
        _patch_loop_deps(monkeypatch, tmp_path, pipeline)

        success, _ = execute_code_review_loop(
            workflow_id="cr-noconfig-001",
            config=None,
        )

        assert success is True
        assert captured["has_base_commit"] is False

    def test_best_effort_step_failure_does_not_abort(
        self, monkeypatch, tmp_path: pathlib.Path
    ) -> None:
        """A non-critical step failure should not abort the loop."""
        from rouge.adw.adw import execute_code_review_loop

        failing_quality = _FakeStep("quality", critical=False, succeed=False)
        clean_step = _CleanOnIterationStep(clean_on=1)
        pipeline = [_FakeStep("generate"), clean_step, failing_quality]
        _patch_loop_deps(monkeypatch, tmp_path, pipeline)

        success, wid = execute_code_review_loop(workflow_id="cr-besteffort-001")

        assert success is True
        assert wid == "cr-besteffort-001"
        # The failing step was called but loop still succeeded
        assert failing_quality.call_count == 1

    def test_context_issue_id_is_none(self, monkeypatch, tmp_path: pathlib.Path) -> None:
        """Codereview loop should create a context with issue_id=None."""
        from rouge.adw.adw import execute_code_review_loop

        captured = {}

        class _CaptureIssueStep(WorkflowStep):
            @property
            def name(self) -> str:
                return "check-issue"

            def run(self, context: WorkflowContext) -> StepResult:
                captured["issue_id"] = context.issue_id
                context.data["review_is_clean"] = True
                return StepResult.ok(data=None)

        pipeline = [_CaptureIssueStep()]
        _patch_loop_deps(monkeypatch, tmp_path, pipeline)

        success, _ = execute_code_review_loop(workflow_id="cr-noissue-001")

        assert success is True
        assert captured["issue_id"] is None
