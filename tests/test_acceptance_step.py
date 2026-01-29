"""Tests for ValidateAcceptanceStep workflow step."""

from unittest.mock import Mock

import pytest

from rouge.core.workflow.artifacts import (
    PatchPlanArtifact,
    PlanArtifact,
)
from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.acceptance import ValidateAcceptanceStep
from rouge.core.workflow.types import (
    PatchPlanData,
    PlanData,
)


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.adw_id = "test-adw-acceptance"
    context.data = {}
    context.artifacts_enabled = True
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


@pytest.fixture
def sample_patch_plan_data():
    """Create a sample PatchPlanData."""
    return PatchPlanData(
        patch_description="Fix typo in documentation",
        original_plan_reference="adw-original-123",
        patch_plan_content="## Patch Plan\n\n### Changes\nFix typo in README.md",
    )


class TestLoadPlanText:
    """Tests for ValidateAcceptanceStep._load_plan_text method."""

    def test_uses_patch_plan_when_available(self, mock_context, sample_patch_plan_data):
        """Test that patch_plan is preferred when available."""
        # Setup: patch_plan_data is in context
        mock_context.data = {"patch_plan_data": sample_patch_plan_data}

        # Setup load_artifact_if_missing to return from context
        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ValidateAcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_patch_plan_data.patch_plan_content

    def test_falls_back_to_plan_when_patch_plan_not_available(self, mock_context, sample_plan_data):
        """Test that plan is used when patch_plan is not available."""
        # Setup: only plan_data is in context
        mock_context.data = {"plan_data": sample_plan_data}

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ValidateAcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_plan_data.plan

    def test_returns_none_when_no_plan_available(self, mock_context):
        """Test that None is returned when neither plan is available."""
        mock_context.data = {}

        def load_artifact_if_missing(_context_key, _artifact_type, _artifact_class, _extract_fn):
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ValidateAcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result is None

    def test_loads_patch_plan_from_artifact(self, mock_context, sample_patch_plan_data):
        """Test loading patch_plan from artifact store."""
        mock_context.data = {}
        patch_plan_artifact = PatchPlanArtifact(
            workflow_id="test-adw",
            patch_plan_data=sample_patch_plan_data,
        )

        call_count = {"count": 0}

        def load_artifact_if_missing(context_key, artifact_type, _artifact_class, extract_fn):
            call_count["count"] += 1
            if artifact_type == "patch_plan":
                value = extract_fn(patch_plan_artifact)
                mock_context.data[context_key] = value
                return value
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ValidateAcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_patch_plan_data.patch_plan_content
        # Should only call once since patch_plan was found
        assert call_count["count"] == 1

    def test_loads_plan_from_artifact_when_patch_plan_missing(self, mock_context, sample_plan_data):
        """Test loading plan from artifact when patch_plan is not available."""
        mock_context.data = {}
        plan_artifact = PlanArtifact(
            workflow_id="test-adw",
            plan_data=sample_plan_data,
        )

        def load_artifact_if_missing(context_key, artifact_type, _artifact_class, extract_fn):
            if artifact_type == "patch_plan":
                return None
            if artifact_type == "plan":
                value = extract_fn(plan_artifact)
                mock_context.data[context_key] = value
                return value
            return None

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ValidateAcceptanceStep()
        result = step._load_plan_text(mock_context)

        assert result == sample_plan_data.plan

    def test_patch_plan_takes_precedence_over_plan(
        self, mock_context, sample_plan_data, sample_patch_plan_data
    ):
        """Test that patch_plan content is returned even when both plan and patch_plan exist."""
        # Both are present in context data
        mock_context.data = {
            "patch_plan_data": sample_patch_plan_data,
            "plan_data": sample_plan_data,
        }

        def load_artifact_if_missing(context_key, _artifact_type, _artifact_class, _extract_fn):
            return mock_context.data.get(context_key)

        mock_context.load_artifact_if_missing = load_artifact_if_missing

        step = ValidateAcceptanceStep()
        result = step._load_plan_text(mock_context)

        # Should use patch_plan, not plan
        assert result == sample_patch_plan_data.patch_plan_content
        assert result != sample_plan_data.plan


class TestValidateAcceptanceStepProperties:
    """Tests for ValidateAcceptanceStep properties."""

    def test_step_name(self):
        """Test that ValidateAcceptanceStep has correct name."""
        step = ValidateAcceptanceStep()
        assert step.name == "Validating plan acceptance"

    def test_step_is_not_critical(self):
        """Test that ValidateAcceptanceStep is not critical."""
        step = ValidateAcceptanceStep()
        assert step.is_critical is False
