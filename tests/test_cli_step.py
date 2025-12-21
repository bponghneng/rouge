"""Tests for step CLI commands."""

from typer.testing import CliRunner

from rouge.cli.cli import app
from rouge.core.workflow.step_registry import reset_step_registry

runner = CliRunner()


class TestStepListCommand:
    """Tests for 'rouge step list' command."""

    def setup_method(self):
        """Reset step registry before each test."""
        reset_step_registry()

    def teardown_method(self):
        """Reset step registry after each test."""
        reset_step_registry()

    def test_step_list_shows_registered_steps(self):
        """Test step list command shows registered steps."""
        result = runner.invoke(app, ["step", "list"])
        assert result.exit_code == 0
        assert "Registered workflow steps" in result.output

        # Check for some expected steps
        assert "Fetching" in result.output
        assert "Classifying" in result.output

    def test_step_list_shows_dependencies(self):
        """Test step list command shows step dependencies."""
        result = runner.invoke(app, ["step", "list"])
        assert result.exit_code == 0
        assert "Dependencies:" in result.output

    def test_step_list_shows_outputs(self):
        """Test step list command shows step outputs."""
        result = runner.invoke(app, ["step", "list"])
        assert result.exit_code == 0
        assert "Outputs:" in result.output

    def test_step_list_shows_criticality(self):
        """Test step list command shows critical/best-effort indicators."""
        result = runner.invoke(app, ["step", "list"])
        assert result.exit_code == 0
        # Should have both critical and best-effort steps
        assert "[critical]" in result.output
        assert "[best-effort]" in result.output


class TestStepDepsCommand:
    """Tests for 'rouge step deps' command."""

    def setup_method(self):
        """Reset step registry before each test."""
        reset_step_registry()

    def teardown_method(self):
        """Reset step registry after each test."""
        reset_step_registry()

    def test_step_deps_shows_dependency_chain(self):
        """Test step deps command shows dependency chain."""
        result = runner.invoke(app, ["step", "deps", "Building implementation plan"])
        assert result.exit_code == 0
        assert "Dependency chain" in result.output

    def test_step_deps_no_dependencies(self):
        """Test step deps command for step with no dependencies."""
        result = runner.invoke(app, ["step", "deps", "Fetching issue from Supabase"])
        assert result.exit_code == 0
        assert "no dependencies" in result.output

    def test_step_deps_unknown_step(self):
        """Test step deps command for unknown step."""
        result = runner.invoke(app, ["step", "deps", "Unknown Step Name"])
        assert result.exit_code == 1
        assert "Unknown step" in result.output or "Error" in result.output


class TestStepValidateCommand:
    """Tests for 'rouge step validate' command."""

    def setup_method(self):
        """Reset step registry before each test."""
        reset_step_registry()

    def teardown_method(self):
        """Reset step registry after each test."""
        reset_step_registry()

    def test_step_validate_valid_registry(self):
        """Test step validate command on valid registry."""
        result = runner.invoke(app, ["step", "validate"])
        # Default registry should be valid
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "no issues" in result.output.lower()


class TestStepRunCommand:
    """Tests for 'rouge step run' command."""

    def test_step_run_missing_options(self):
        """Test step run command requires issue-id and adw-id."""
        result = runner.invoke(app, ["step", "run", "Test Step"])
        assert result.exit_code != 0
        # Should show error about missing required option (check output, which includes stderr)
        assert "Missing option" in result.output or "required" in result.output.lower()

    def test_step_run_unknown_step(self):
        """Test step run command with unknown step name."""
        result = runner.invoke(
            app,
            ["step", "run", "Unknown Step", "--issue-id", "1", "--adw-id", "test-123"],
        )
        assert result.exit_code == 1
        assert "Error" in result.output or "not found" in result.output.lower()
