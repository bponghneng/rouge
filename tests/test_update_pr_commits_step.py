"""Tests for UpdatePRCommitsStep workflow step.

Tests focus on git CLI detection (gh/glab) for PR/MR platform detection,
verifying that the step works independently without loading parent artifacts.
"""

import json
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
    """Tests for _detect_pr_platform via gh/glab CLI tools."""

    def test_detects_github_pr_via_gh(self, mock_context):
        """Test detection of GitHub PR using gh CLI."""
        step = UpdatePRCommitsStep()
        gh_output = json.dumps({"url": "https://github.com/org/repo/pull/42"})
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = gh_output

        with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/gh" if cmd == "gh" else None):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform == "github"
        assert url == "https://github.com/org/repo/pull/42"
        # Verify gh was called with correct args
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gh", "pr", "view", "--json", "url"]

    def test_detects_gitlab_mr_via_glab(self, mock_context):
        """Test detection of GitLab MR using glab CLI when gh is not available."""
        step = UpdatePRCommitsStep()
        glab_output = json.dumps({"web_url": "https://gitlab.com/org/repo/-/merge_requests/7"})
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = glab_output

        with patch(
            "shutil.which", side_effect=lambda cmd: "/usr/bin/glab" if cmd == "glab" else None
        ):
            with patch("subprocess.run", return_value=mock_result) as mock_run:
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform == "gitlab"
        assert url == "https://gitlab.com/org/repo/-/merge_requests/7"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["glab", "mr", "view", "--output", "json"]

    def test_github_tried_first_before_gitlab(self, mock_context):
        """Test that gh is tried before glab when both are available."""
        step = UpdatePRCommitsStep()
        gh_output = json.dumps({"url": "https://github.com/org/repo/pull/1"})
        mock_gh_result = Mock()
        mock_gh_result.returncode = 0
        mock_gh_result.stdout = gh_output

        with patch("shutil.which", return_value="/usr/bin/tool"):
            with patch("subprocess.run", return_value=mock_gh_result):
                platform, url = step._detect_pr_platform("/fake/repo")

        # Should detect GitHub since gh is tried first
        assert platform == "github"
        assert url == "https://github.com/org/repo/pull/1"

    def test_falls_back_to_gitlab_when_gh_fails(self, mock_context):
        """Test fallback to glab when gh command fails."""
        step = UpdatePRCommitsStep()

        gh_result = Mock()
        gh_result.returncode = 1
        gh_result.stdout = ""

        glab_output = json.dumps({"web_url": "https://gitlab.com/org/repo/-/merge_requests/3"})
        glab_result = Mock()
        glab_result.returncode = 0
        glab_result.stdout = glab_output

        def mock_which(cmd):
            return f"/usr/bin/{cmd}" if cmd in ("gh", "glab") else None

        def mock_run(cmd, **kwargs):
            if cmd[0] == "gh":
                return gh_result
            return glab_result

        with patch("shutil.which", side_effect=mock_which):
            with patch("subprocess.run", side_effect=mock_run):
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform == "gitlab"
        assert url == "https://gitlab.com/org/repo/-/merge_requests/3"

    def test_returns_none_when_no_cli_available(self, mock_context):
        """Test returns (None, None) when neither gh nor glab is available."""
        step = UpdatePRCommitsStep()

        with patch("shutil.which", return_value=None):
            platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None

    def test_returns_none_when_both_cli_fail(self, mock_context):
        """Test returns (None, None) when both gh and glab commands fail."""
        step = UpdatePRCommitsStep()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stdout = ""

        with patch("shutil.which", return_value="/usr/bin/tool"):
            with patch("subprocess.run", return_value=fail_result):
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None

    def test_handles_gh_timeout(self, mock_context):
        """Test handles timeout from gh command gracefully."""
        step = UpdatePRCommitsStep()

        def mock_which(cmd):
            return f"/usr/bin/{cmd}" if cmd in ("gh", "glab") else None

        call_count = {"gh": 0, "glab": 0}

        def mock_run(cmd, **kwargs):
            if cmd[0] == "gh":
                call_count["gh"] += 1
                raise subprocess.TimeoutExpired(cmd="gh", timeout=30)
            # glab also fails
            call_count["glab"] += 1
            result = Mock()
            result.returncode = 1
            result.stdout = ""
            return result

        with patch("shutil.which", side_effect=mock_which):
            with patch("subprocess.run", side_effect=mock_run):
                platform, url = step._detect_pr_platform("/fake/repo")

        assert platform is None
        assert url is None
        assert call_count["gh"] == 1

    def test_handles_invalid_json_from_gh(self, mock_context):
        """Test handles invalid JSON output from gh gracefully."""
        step = UpdatePRCommitsStep()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"

        with patch("shutil.which", side_effect=lambda cmd: "/usr/bin/gh" if cmd == "gh" else None):
            with patch("subprocess.run", return_value=mock_result):
                platform, url = step._detect_pr_platform("/fake/repo")

        # Should fall through to (None, None) since glab is not available
        assert platform is None
        assert url is None


class TestRunSkipsWhenNoCli:
    """Tests for UpdatePRCommitsStep.run when no CLI tools are available."""

    def test_skips_when_no_cli_tools(self, mock_context):
        """Test step returns success with skip message when no CLI tools found."""
        step = UpdatePRCommitsStep()

        with patch("rouge.core.workflow.steps.update_pr_commits.get_repo_path", return_value="/repo"):
            with patch("shutil.which", return_value=None):
                with patch(
                    "rouge.core.workflow.steps.update_pr_commits.emit_comment_from_payload",
                    return_value=("success", "ok"),
                ):
                    result = step.run(mock_context)

        assert result.success is True  # Non-critical, returns ok


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
