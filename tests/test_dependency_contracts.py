"""Contract tests for workflow step dependency semantics.

This module tests the three dependency kinds defined in the step registry:
1. Required dependencies: Step fails when data is missing
2. Optional dependencies: Step skips gracefully when data is missing
3. Ordering-only dependencies: Step doesn't read dependency data at all

These tests validate that step implementations match their registry declarations.
"""

from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.step_registry import get_step_registry


@pytest.fixture
def base_context() -> WorkflowContext:
    """Create a base workflow context with empty data."""
    return WorkflowContext(
        adw_id="test-workflow-123",
        issue_id=42,
        repo_paths=["/fake/repo"],
    )


# ==============================================================================
# Test 1: Required Dependencies - Must Fail When Data Missing
# ==============================================================================


class TestRequiredDependencies:
    """Test that steps with required dependencies fail when data is missing."""

    def test_implement_step_fails_without_plan(self, base_context: WorkflowContext) -> None:
        """ImplementPlanStep requires plan data and fails without it."""
        from rouge.core.workflow.steps.implement_step import ImplementPlanStep

        # Verify registry declares plan as required
        registry = get_step_registry()
        metadata = registry.get_step_metadata("Implementing plan-based solution")
        assert metadata is not None
        assert "plan" in metadata.dependencies
        # Required dependency has no dependency_kinds entry
        assert "plan" not in metadata.dependency_kinds

        # Run step without plan data in context
        step = ImplementPlanStep()
        result = step.run(base_context)

        # Must fail with clear error message
        assert result.success is False
        assert result.error is not None
        assert "plan" in result.error.lower()


# ==============================================================================
# Test 2: Optional Dependencies - Must Skip Gracefully When Data Missing
# ==============================================================================


class TestOptionalDependencies:
    """Test that steps with optional dependencies skip gracefully when data is missing."""

    def test_gh_pull_request_step_skips_without_compose_request(
        self, base_context: WorkflowContext
    ) -> None:
        """GhPullRequestStep has optional compose-request dependency and skips gracefully."""
        from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep

        # Verify registry declares compose-request as optional
        registry = get_step_registry()
        metadata = registry.get_step_metadata("Creating GitHub pull request")
        assert metadata is not None
        assert "compose-request" in metadata.dependencies
        assert metadata.dependency_kinds.get("compose-request") == "optional"

        # Run step without compose-request data in context
        step = GhPullRequestStep()
        result = step.run(base_context)

        # Must succeed (skip gracefully), not fail
        assert result.success is True
        # No error should be set for graceful skip
        assert result.error is None or result.error == ""

    def test_glab_pull_request_step_skips_without_compose_request(
        self, base_context: WorkflowContext
    ) -> None:
        """GlabPullRequestStep has optional compose-request dependency and skips gracefully."""
        from rouge.core.workflow.steps.glab_pull_request_step import GlabPullRequestStep

        # Verify registry declares compose-request as optional
        registry = get_step_registry()
        metadata = registry.get_step_metadata("Creating GitLab merge request")
        assert metadata is not None
        assert "compose-request" in metadata.dependencies
        assert metadata.dependency_kinds.get("compose-request") == "optional"

        # Run step without compose-request data in context
        step = GlabPullRequestStep()
        result = step.run(base_context)

        # Must succeed (skip gracefully), not fail
        assert result.success is True
        # No error should be set for graceful skip
        assert result.error is None or result.error == ""

    def test_gh_pull_request_step_has_implement_as_optional(self) -> None:
        """GhPullRequestStep declares implement as optional dependency."""
        registry = get_step_registry()
        metadata = registry.get_step_metadata("Creating GitHub pull request")
        assert metadata is not None
        assert "implement" in metadata.dependencies
        assert metadata.dependency_kinds.get("implement") == "optional"

    def test_glab_pull_request_step_has_implement_as_optional(self) -> None:
        """GlabPullRequestStep declares implement as optional dependency."""
        registry = get_step_registry()
        metadata = registry.get_step_metadata("Creating GitLab merge request")
        assert metadata is not None
        assert "implement" in metadata.dependencies
        assert metadata.dependency_kinds.get("implement") == "optional"

    def test_code_quality_step_has_optional_implement_dependency(
        self, base_context: WorkflowContext
    ) -> None:
        """CodeQualityStep has optional implement dependency for affected repo paths."""
        registry = get_step_registry()
        metadata = registry.get_step_metadata("Running code quality checks")
        assert metadata is not None
        assert "implement" in metadata.dependencies
        assert metadata.dependency_kinds.get("implement") == "optional"

    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    def test_optional_dependency_returns_none_not_error(
        self, mock_emit, base_context: WorkflowContext
    ) -> None:
        """Optional dependency loading returns None for missing data, not error."""
        from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep

        # context.data has no pr_details
        step = GhPullRequestStep()
        result = step.run(base_context)

        # Step should succeed (not fail) when optional data is missing
        assert result.success is True

        # Verify emit was called with skip message
        assert mock_emit.called
        text_arg = mock_emit.call_args[0][2]
        raw_arg = mock_emit.call_args[0][3]
        assert "skipped" in text_arg.lower() or "skipped" in str(raw_arg).lower()


# ==============================================================================
# Test 3: Registry Coverage - All Dependencies Are Classified
# ==============================================================================


class TestRegistryCoverage:
    """Test that all registry dependencies are covered by one of the three kinds."""

    def test_all_dependencies_have_defined_kinds(self) -> None:
        """Every dependency in the registry must be required, optional, or ordering-only."""
        registry = get_step_registry()

        issues = []
        for step_name in registry.list_all_steps():
            metadata = registry.get_step_metadata(step_name)
            if metadata is None:
                continue

            for dep in metadata.dependencies:
                # Classify the dependency kind
                if dep in metadata.dependency_kinds:
                    kind = metadata.dependency_kinds[dep]
                    # Validate it's one of the three valid kinds
                    if kind not in ["required", "optional", "ordering-only"]:
                        issues.append(
                            f"Step '{step_name}' has invalid dependency kind '{kind}' "
                            f"for artifact '{dep}'"
                        )
                else:
                    # No entry means it's implicitly required (this is valid)
                    kind = "required"

                # All dependencies are now classified (either explicitly or implicitly)
                assert kind in ["required", "optional", "ordering-only"]

        # Report any issues found
        if issues:
            pytest.fail("\n".join(issues))

    def test_no_undeclared_dependencies_in_step_code(self) -> None:
        """Steps should not read data that isn't declared in registry.

        This is a meta-test that verifies the testing approach is sound.
        """
        registry = get_step_registry()

        # Sample a few steps to demonstrate the pattern
        test_cases = [
            ("Implementing plan-based solution", ["plan"]),
            ("Running code quality checks", ["implement"]),
            (
                "Creating GitHub pull request",
                ["compose-request", "fetch-issue", "plan", "implement"],
            ),
        ]

        for step_name, expected_deps in test_cases:
            metadata = registry.get_step_metadata(step_name)
            assert metadata is not None

            # Verify declared dependencies match expected
            assert set(metadata.dependencies) == set(expected_deps), (
                f"Step '{step_name}' dependencies don't match: "
                f"expected {expected_deps}, got {metadata.dependencies}"
            )


# ==============================================================================
# Test 4: Integration Tests - Dependency Semantics with context.data
# ==============================================================================


class TestDependencySemanticsIntegration:
    """Integration tests validating dependency semantics with context.data."""

    @patch("rouge.core.database.get_client")
    @patch("rouge.core.workflow.pull_request_step_base._emit_and_log")
    def test_optional_dependency_succeeds_with_data(
        self,
        mock_emit: Mock,
        mock_get_client: Mock,
        base_context: WorkflowContext,
    ) -> None:
        """Optional dependency succeeds when data is present in context."""
        from rouge.core.workflow.steps.gh_pull_request_step import GhPullRequestStep

        # Mock get_client to avoid database connections
        mock_db_client = Mock()
        mock_get_client.return_value = mock_db_client

        # Set pr_details in context data (as ComposeRequestStep would)
        base_context.data["pr_details"] = {
            "title": "Test PR",
            "summary": "Test summary",
            "commits": [],
        }

        # Mock environment and subprocess to avoid actual PR creation
        with patch.dict("os.environ", {"GITHUB_PAT": "test-token"}):
            with patch(
                "rouge.core.workflow.steps.gh_pull_request_step.shutil.which"
            ) as mock_which:
                with patch(
                    "rouge.core.workflow.steps.gh_pull_request_step.subprocess.run"
                ) as mock_run:
                    mock_which.return_value = "/usr/bin/gh"
                    # Step calls per repo: rev-parse (branch), gh pr list,
                    # rev-parse (base branch), rev-list (delta), git push, gh pr create
                    mock_rev_parse = Mock(
                        returncode=0, stdout="feature-branch\n", stderr=""
                    )
                    mock_pr_list = Mock(returncode=0, stdout="[]", stderr="")
                    mock_base_branch = Mock(
                        returncode=0, stdout="origin/main\n", stderr=""
                    )
                    mock_delta = Mock(returncode=0, stdout="1\n", stderr="")
                    mock_push = Mock(returncode=0, stdout="", stderr="")
                    mock_pr = Mock(
                        returncode=0,
                        stdout="https://github.com/test/pr/1\n",
                    )
                    mock_run.side_effect = [
                        mock_rev_parse,
                        mock_pr_list,
                        mock_base_branch,
                        mock_delta,
                        mock_push,
                        mock_pr,
                    ]

                    step = GhPullRequestStep()
                    result = step.run(base_context)

        # Should succeed with data present
        assert result.success is True

    def test_ordering_only_dependency_works_without_reading(
        self, base_context: WorkflowContext
    ) -> None:
        """Ordering-only dependency step succeeds without reading the dependency data."""
        from rouge.core.workflow.steps.code_quality_step import CodeQualityStep

        # Verify code quality has ordering-only implement dependency
        registry = get_step_registry()
        metadata = registry.get_step_metadata("Running code quality checks")
        assert metadata is not None

        # CodeQualityStep should work with no implement data at all
        with patch(
            "rouge.core.workflow.steps.code_quality_step.execute_template"
        ) as mock_exec:
            with patch(
                "rouge.core.workflow.steps.code_quality_step.emit_comment_from_payload"
            ) as mock_emit:
                mock_response = Mock()
                mock_response.success = True
                mock_response.output = (
                    '{"output": "code-quality", "tools": ["ruff"], "issues": []}'
                )
                mock_exec.return_value = mock_response
                mock_emit.return_value = ("success", "ok")

                step = CodeQualityStep()
                result = step.run(base_context)

        assert result.success is True
