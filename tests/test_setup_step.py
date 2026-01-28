"""Tests for SetupStep git environment setup."""

import subprocess
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.setup import GIT_TIMEOUT, SetupStep
from rouge.core.workflow.types import StepResult


@pytest.fixture
def context():
    """Create a sample workflow context for testing."""
    return WorkflowContext(issue_id=1, adw_id="test123")


# === Basic Step Properties Tests ===


def test_setup_step_name():
    """Test SetupStep has correct name."""
    step = SetupStep()
    assert step.name == "Setting up git environment"


def test_setup_step_is_critical():
    """Test SetupStep is marked as critical."""
    step = SetupStep()
    assert step.is_critical is True


# === Successful Execution Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_success(mock_subprocess, mock_get_repo_path, _mock_update_branch, context):
    """Test successful git setup with all commands succeeding."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock all three git commands succeeding
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 0
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = ""

    mock_reset_result = Mock()
    mock_reset_result.returncode = 0
    mock_reset_result.stdout = ""
    mock_reset_result.stderr = ""

    mock_create_branch_result = Mock()
    mock_create_branch_result.returncode = 0
    mock_create_branch_result.stdout = ""
    mock_create_branch_result.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout_result,
        mock_reset_result,
        mock_create_branch_result,
    ]

    step = SetupStep()
    result = step.run(context)

    assert result.success is True
    assert result.error is None
    assert mock_subprocess.call_count == 3

    # Verify git checkout main was called first
    checkout_call = mock_subprocess.call_args_list[0]
    assert checkout_call[0][0] == ["git", "checkout", "main"]
    assert checkout_call[1]["cwd"] == "/path/to/repo"
    assert checkout_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git reset was called second
    reset_call = mock_subprocess.call_args_list[1]
    assert reset_call[0][0] == ["git", "reset", "--hard", "origin/main"]
    assert reset_call[1]["cwd"] == "/path/to/repo"
    assert reset_call[1]["timeout"] == GIT_TIMEOUT

    # Verify git checkout -b was called third
    branch_call = mock_subprocess.call_args_list[2]
    assert branch_call[0][0] == ["git", "checkout", "-b", "adw-test123"]
    assert branch_call[1]["cwd"] == "/path/to/repo"
    assert branch_call[1]["timeout"] == GIT_TIMEOUT


@patch.dict(
    "os.environ", {"DEFAULT_GIT_BRANCH": "develop", "ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"}
)
@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_custom_default_branch(
    mock_subprocess, mock_get_repo_path, _mock_update_branch, context
):
    """Test setup uses custom DEFAULT_GIT_BRANCH from environment."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = SetupStep()
    result = step.run(context)

    assert result.success is True

    # Verify custom branch was used in checkout
    checkout_call = mock_subprocess.call_args_list[0]
    assert checkout_call[0][0] == ["git", "checkout", "develop"]

    # Verify custom branch was used in reset
    reset_call = mock_subprocess.call_args_list[1]
    assert reset_call[0][0] == ["git", "reset", "--hard", "origin/develop"]


@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_default_branch_fallback(
    mock_subprocess, mock_get_repo_path, _mock_update_branch, context, monkeypatch
):
    """Test setup defaults to 'main' when DEFAULT_GIT_BRANCH is not set."""
    monkeypatch.delenv("DEFAULT_GIT_BRANCH", raising=False)
    monkeypatch.setenv("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", "true")
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = SetupStep()
    result = step.run(context)

    assert result.success is True

    # Verify default 'main' branch was used
    checkout_call = mock_subprocess.call_args_list[0]
    assert checkout_call[0][0] == ["git", "checkout", "main"]

    reset_call = mock_subprocess.call_args_list[1]
    assert reset_call[0][0] == ["git", "reset", "--hard", "origin/main"]


# === Safety Check Tests ===


def test_setup_step_destructive_ops_not_allowed_by_default(context, monkeypatch):
    """Test setup fails when ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS is not set."""
    monkeypatch.delenv("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", raising=False)
    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "Destructive git operations not allowed" in result.error
    assert "ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS=true" in result.error


def test_setup_step_destructive_ops_explicitly_disabled(context, monkeypatch):
    """Test setup fails when ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS is explicitly set to false."""
    monkeypatch.setenv("ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS", "false")
    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "Destructive git operations not allowed" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "True"})
@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_destructive_ops_case_insensitive(
    mock_subprocess, mock_get_repo_path, _mock_update_branch, context
):
    """Test setup accepts 'True' (capital T) for ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = SetupStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 3


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "TRUE"})
@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_destructive_ops_uppercase(
    mock_subprocess, mock_get_repo_path, _mock_update_branch, context
):
    """Test setup accepts 'TRUE' (all caps) for ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = SetupStep()
    result = step.run(context)

    assert result.success is True
    assert mock_subprocess.call_count == 3


# === Failure Handling Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_checkout_failure(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles git checkout failure."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock checkout failure
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 1
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = "error: pathspec 'main' did not match any file(s)"
    mock_subprocess.return_value = mock_checkout_result

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "git checkout main failed" in result.error
    assert "exit code 1" in result.error
    assert "pathspec 'main' did not match" in result.error
    assert mock_subprocess.call_count == 1  # Should stop after checkout fails


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_reset_failure(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles git reset failure."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock checkout success, reset failure
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 0
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = ""

    mock_reset_result = Mock()
    mock_reset_result.returncode = 1
    mock_reset_result.stdout = ""
    mock_reset_result.stderr = "fatal: ambiguous argument 'origin/main'"

    mock_subprocess.side_effect = [mock_checkout_result, mock_reset_result]

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "git reset --hard origin/main failed" in result.error
    assert "exit code 1" in result.error
    assert "ambiguous argument" in result.error
    assert mock_subprocess.call_count == 2  # Should stop after reset fails


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_branch_creation_failure(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles git checkout -b failure."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock checkout and reset success, branch creation failure
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 0
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = ""

    mock_reset_result = Mock()
    mock_reset_result.returncode = 0
    mock_reset_result.stdout = ""
    mock_reset_result.stderr = ""

    mock_branch_result = Mock()
    mock_branch_result.returncode = 128
    mock_branch_result.stdout = ""
    mock_branch_result.stderr = "fatal: A branch named 'adw-test123' already exists"

    mock_subprocess.side_effect = [mock_checkout_result, mock_reset_result, mock_branch_result]

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "git checkout -b adw-test123 failed" in result.error
    assert "exit code 128" in result.error
    assert "already exists" in result.error
    assert mock_subprocess.call_count == 3


# === Timeout Handling Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_checkout_timeout(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles timeout on git checkout."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_subprocess.side_effect = subprocess.TimeoutExpired(
        cmd=["git", "checkout", "main"], timeout=GIT_TIMEOUT
    )

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error
    assert str(GIT_TIMEOUT) in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_reset_timeout(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles timeout on git reset."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock checkout success, reset timeout
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 0
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout_result,
        subprocess.TimeoutExpired(
            cmd=["git", "reset", "--hard", "origin/main"], timeout=GIT_TIMEOUT
        ),
    ]

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_branch_creation_timeout(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles timeout on git checkout -b."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock checkout and reset success, branch creation timeout
    mock_checkout_result = Mock()
    mock_checkout_result.returncode = 0
    mock_checkout_result.stdout = ""
    mock_checkout_result.stderr = ""

    mock_reset_result = Mock()
    mock_reset_result.returncode = 0
    mock_reset_result.stdout = ""
    mock_reset_result.stderr = ""

    mock_subprocess.side_effect = [
        mock_checkout_result,
        mock_reset_result,
        subprocess.TimeoutExpired(
            cmd=["git", "checkout", "-b", "adw-test123"], timeout=GIT_TIMEOUT
        ),
    ]

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "timed out after" in result.error


# === Error Handling Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_git_not_found(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles git command not found."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_subprocess.side_effect = FileNotFoundError("git not found")

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "git command not found" in result.error
    assert "ensure git is installed" in result.error


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_unexpected_error(mock_subprocess, mock_get_repo_path, context):
    """Test setup handles unexpected exceptions."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_subprocess.side_effect = RuntimeError("Unexpected system error")

    step = SetupStep()
    result = step.run(context)

    assert result.success is False
    assert "Unexpected error during git setup" in result.error
    assert "RuntimeError" in result.error
    assert "Unexpected system error" in result.error


# === Branch Name Formatting Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_branch_name_format(mock_subprocess, mock_get_repo_path, _mock_update_branch):
    """Test that branch name is correctly formatted from adw_id."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    # Test with various adw_id values
    test_cases = [
        ("abc123", "adw-abc123"),
        ("workflow-456", "adw-workflow-456"),
        ("12345", "adw-12345"),
    ]

    for adw_id, expected_branch in test_cases:
        mock_subprocess.reset_mock()
        context = WorkflowContext(issue_id=1, adw_id=adw_id)

        step = SetupStep()
        result = step.run(context)

        assert result.success is True
        branch_call = mock_subprocess.call_args_list[2]
        assert branch_call[0][0] == ["git", "checkout", "-b", expected_branch]


# === Subprocess Options Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_subprocess_options(
    mock_subprocess, mock_get_repo_path, _mock_update_branch, context
):
    """Test that subprocess.run is called with correct options."""
    mock_get_repo_path.return_value = "/path/to/repo"

    # Mock all git commands succeeding
    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = SetupStep()
    step.run(context)

    # All calls should have these common options
    for call in mock_subprocess.call_args_list:
        kwargs = call[1]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == GIT_TIMEOUT
        assert kwargs["cwd"] == "/path/to/repo"


# === Integration with StepResult Tests ===


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.update_issue_branch")
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_returns_step_result_ok(
    mock_subprocess, mock_get_repo_path, _mock_update_branch, context
):
    """Test successful execution returns StepResult.ok()."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_result = Mock()
    mock_result.returncode = 0
    mock_result.stdout = ""
    mock_result.stderr = ""
    mock_subprocess.return_value = mock_result

    step = SetupStep()
    result = step.run(context)

    assert isinstance(result, StepResult)
    assert result.success is True
    assert result.data is None  # SetupStep returns None on success
    assert result.error is None


@patch.dict("os.environ", {"ROUGE_ALLOW_DESTRUCTIVE_GIT_OPS": "true"})
@patch("rouge.core.workflow.steps.setup.get_repo_path")
@patch("rouge.core.workflow.steps.setup.subprocess.run")
def test_setup_step_returns_step_result_fail(mock_subprocess, mock_get_repo_path, context):
    """Test failed execution returns StepResult.fail()."""
    mock_get_repo_path.return_value = "/path/to/repo"

    mock_result = Mock()
    mock_result.returncode = 1
    mock_result.stdout = ""
    mock_result.stderr = "error message"
    mock_subprocess.return_value = mock_result

    step = SetupStep()
    result = step.run(context)

    assert isinstance(result, StepResult)
    assert result.success is False
    assert result.data is None
    assert result.error is not None
    assert len(result.error) > 0
