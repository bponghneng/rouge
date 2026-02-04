"""Tests for UpdatePRCommitsStep workflow step.

Tests focus on platform selection via DEV_SEC_OPS_PLATFORM and git CLI detection,
verifying that the step works independently without loading parent artifacts.
"""

import json
import os
import subprocess
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.update_pr_commits import UpdatePRCommitsStep


@pytest.fixture
def mock_context():
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-pr-update"
    context.data = {}
    context.artifacts_enabled = True
    context.artifact_store = Mock()
    return context


class TestDetectPrPlatform:
    """Tests for _detect_pr_platform via DEV_SEC_OPS_PLATFORM."""

    def test_detects_github_pr_via_gh(self):
        """Test detection of GitHub PR using gh CLI."""
        step = UpdatePRCommitsStep()
        gh_output = json.dumps({"url": "https://github.com/org/repo/pull/42"})
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = gh_output

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "github"}):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform == "github"
        assert url == "https://github.com/org/repo/pull/42"
        # Verify gh was called with correct args
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gh", "pr", "view", "--json", "url"]

    def test_detects_gitlab_mr_via_glab(self):
        """Test detection of GitLab MR using glab CLI."""
        step = UpdatePRCommitsStep()
        glab_output = json.dumps({"web_url": "https://gitlab.com/org/repo/-/merge_requests/7"})
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = glab_output

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "gitlab"}):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform == "gitlab"
        assert url == "https://gitlab.com/org/repo/-/merge_requests/7"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["glab", "mr", "view", "--output", "json"]

    def test_returns_none_when_env_missing(self):
        """Test returns (None, None) when DEV_SEC_OPS_PLATFORM is unset."""
        step = UpdatePRCommitsStep()

        # Create a copy of environ without DEV_SEC_OPS_PLATFORM
        env_without_platform = {k: v for k, v in os.environ.items() if k != "DEV_SEC_OPS_PLATFORM"}

        with patch.dict("os.environ", env_without_platform, clear=True):
            with patch("subprocess.run") as mock_run:
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None
        mock_run.assert_not_called()

    def test_returns_none_when_env_invalid(self):
        """Test returns (None, None) when DEV_SEC_OPS_PLATFORM is invalid."""
        step = UpdatePRCommitsStep()

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "bitbucket"}):
            with patch("subprocess.run") as mock_run:
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None
        mock_run.assert_not_called()

    def test_returns_none_when_cli_missing(self):
        """Test returns (None, None) when CLI is missing."""
        step = UpdatePRCommitsStep()

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "github"}):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None

    def test_returns_none_when_github_cli_fails(self):
        """Test returns (None, None) when the selected CLI command fails."""
        step = UpdatePRCommitsStep()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stdout = ""

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "github"}):
            with patch("subprocess.run", return_value=fail_result):
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None

    def test_handles_gh_timeout(self):
        """Test handles timeout from gh command gracefully."""
        step = UpdatePRCommitsStep()

        def mock_run(cmd, **kwargs):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "github"}):
            with patch("subprocess.run", side_effect=mock_run):
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None

    def test_handles_invalid_json_from_gh(self):
        """Test handles invalid JSON output from gh gracefully."""
        step = UpdatePRCommitsStep()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"

        with patch.dict("os.environ", {"DEV_SEC_OPS_PLATFORM": "github"}):
            with patch("subprocess.run", return_value=mock_result):
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None


class TestRunWhenPlatformMissing:
    """Tests for UpdatePRCommitsStep.run when platform cannot be detected."""

    def test_fails_when_env_missing(self, mock_context):
        """Test step fails when DEV_SEC_OPS_PLATFORM is not set."""
        step = UpdatePRCommitsStep()

        # Create a copy of environ without DEV_SEC_OPS_PLATFORM
        env_without_platform = {k: v for k, v in os.environ.items() if k != "DEV_SEC_OPS_PLATFORM"}

        with patch(
            "rouge.core.workflow.steps.update_pr_commits.get_repo_path", return_value="/repo"
        ):
            with patch.dict("os.environ", env_without_platform, clear=True):
                with patch(
                    "rouge.core.workflow.steps.update_pr_commits.emit_comment_from_payload",
                    return_value=("success", "ok"),
                ):
                    result = step.run(mock_context)

        assert result.success is False


class TestUpdatePRCommitsStepProperties:
    """Tests for UpdatePRCommitsStep properties."""

    def test_step_name(self):
        """Test step has correct name."""
        step = UpdatePRCommitsStep()
        assert step.name == "Updating pull request with patch commits"

    def test_step_is_not_critical(self):
        """Test step is not critical."""
        step = UpdatePRCommitsStep()
        assert step.is_critical is False
