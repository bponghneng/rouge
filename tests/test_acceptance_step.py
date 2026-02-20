"""Tests for AcceptanceStep workflow step."""

from unittest.mock import Mock

import pytest

from rouge.core.workflow.artifacts import (
    PlanArtifact,
)
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.acceptance_step import AcceptanceStep
from rouge.core.workflow.types import (
    PlanData,
)


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-acceptance"
    context.data = {}
    context.artifact_store = Mock()
    return context


@pytest.fixture
def sample_plan_data():
    """Create a sample PlanData."""
    return PlanData(
        plan="## Plan\n\n### Step 1\nImplement feature X",
        summary="Implement feature X",
        session_id="session-123",
    )


class TestLoadPlanText:
    """Tests for AcceptanceStep._load_plan_text method."""

    def test_uses_plan_when_available(self, mock_context, sample_plan_data):
        """Test that plan is used when available in context (cache hit)."""
        mock_context.data = {"plan_data": sample_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_required_artifact = load_required_artifact

        step = AcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_plan_data.plan

    def test_returns_none_when_no_plan_available(self, mock_context):
        """Test that None is returned when no plan is available (load_required_artifact raises)."""
        mock_context.data = {}

        def load_required_artifact(_context_key, _artifact_type, _artifact_class, _extract_fn):
            raise Exception("Required artifact 'plan' not found")

        mock_context.load_required_artifact = load_required_artifact

        step = AcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result is None

    def test_loads_plan_from_artifact(self, mock_context, sample_plan_data):
        """Test loading plan from artifact store via load_required_artifact."""
        mock_context.data = {}
        plan_artifact = PlanArtifact(
            workflow_id="test-adw",
            plan_data=sample_plan_data,
        )

        def load_required_artifact(context_key, artifact_type, _artifact_class, extract_fn):
            if artifact_type == "plan":
                value = extract_fn(plan_artifact)
                mock_context.data[context_key] = value
                return value
            raise Exception(f"Required artifact '{artifact_type}' not found")

        mock_context.load_required_artifact = load_required_artifact

        step = AcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_plan_data.plan

    def test_patch_workflow_plan_loaded_as_plan_artifact(self, mock_context):
        """Test that patch workflows use PlanArtifact (not a separate PatchPlanArtifact).

        After decoupling, both main and patch workflows store plans as PlanArtifact.
        """
        patch_plan_data = PlanData(
            plan="## Patch Plan\n\n### Changes\nFix typo in README.md",
            summary="Plan for patch: Fix typo in documentation",
        )
        mock_context.data = {"plan_data": patch_plan_data}

        def load_required_artifact(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_required_artifact = load_required_artifact

        step = AcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result == patch_plan_data.plan
        assert "Patch Plan" in result


class TestAcceptanceStepProperties:
    """Tests for AcceptanceStep properties."""

    def test_step_name(self):
        """Test that AcceptanceStep has correct name."""
        step = AcceptanceStep()
        assert step.name == "Validating plan acceptance"

    def test_step_is_not_critical(self):
        """Test that AcceptanceStep is not critical."""
        step = AcceptanceStep()
        assert step.is_critical is False
