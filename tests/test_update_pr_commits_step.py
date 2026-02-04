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

        # Mock compose-commits dependencies (runs before platform detection)
        mock_response = Mock(success=True, output='{"output": "commits-composed"}')
        mock_parse = Mock(success=True, data={"output": "commits-composed"}, error=None)
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"

        with patch(
            "rouge.core.workflow.steps.update_pr_commits.get_repo_path", return_value="/repo"
        ):
            with patch(
                "rouge.core.workflow.steps.update_pr_commits.make_progress_comment_handler",
                return_value=lambda x: None,
            ):
                with patch(
                    "rouge.core.workflow.steps.update_pr_commits.ClaudeAgentTemplateRequest",
                    return_value=mock_request_instance,
                ):
                    with patch(
                        "rouge.core.workflow.steps.update_pr_commits.execute_template",
                        return_value=mock_response,
                    ):
                        with patch(
                            "rouge.core.workflow.steps.update_pr_commits.parse_and_validate_json",
                            return_value=mock_parse,
                        ):
                            with patch.dict("os.environ", env_without_platform, clear=True):
                                with patch(
                                    "rouge.core.workflow.steps.update_pr_commits.emit_comment_from_payload",
                                    return_value=("success", "ok"),
                                ):
                                    result = step.run(mock_context)

        assert result.success is False


class TestComposeCommits:
    """Tests for compose-commits integration in UpdatePRCommitsStep.run."""

    def test_compose_commits_called_before_push(self, mock_context):
        """Test that execute_template is called with /adw-compose-commits before push."""
        step = UpdatePRCommitsStep()

        mock_response = Mock(success=True, output='{"output": "commits-composed"}')
        mock_parse = Mock(success=True, data={"output": "commits-composed"}, error=None)

        # Mock ClaudeAgentTemplateRequest to bypass Pydantic slash_command validation
        mock_request_instance = Mock(
            slash_command="/adw-compose-commits",
            agent_name="commit_composer",
        )
        mock_request_instance.model_dump_json.return_value = "{}"

        # Mock subprocess.run for branch check and push
        branch_result = Mock(returncode=0, stdout="feature-branch\n", stderr="")
        push_result = Mock(returncode=0, stdout="", stderr="")

        def subprocess_side_effect(cmd, **_kwargs):
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return branch_result
            if cmd[0] == "git" and cmd[1] == "push":
                return push_result
            # gh pr view for platform detection
            return Mock(
                returncode=0,
                stdout=json.dumps({"url": "https://github.com/org/repo/pull/1"}),
            )

        with patch(
            "rouge.core.workflow.steps.update_pr_commits.get_repo_path", return_value="/repo"
        ):
            with patch(
                "rouge.core.workflow.steps.update_pr_commits.make_progress_comment_handler",
                return_value=lambda x: None,
            ):
                with patch(
                    "rouge.core.workflow.steps.update_pr_commits.ClaudeAgentTemplateRequest",
                    return_value=mock_request_instance,
                ):
                    with patch(
                        "rouge.core.workflow.steps.update_pr_commits.execute_template",
                        return_value=mock_response,
                    ) as mock_exec:
                        with patch(
                            "rouge.core.workflow.steps.update_pr_commits.parse_and_validate_json",
                            return_value=mock_parse,
                        ):
                            with patch.dict(
                                "os.environ",
                                {"DEV_SEC_OPS_PLATFORM": "github", "GITHUB_PAT": "fake-token"},
                            ):
                                with patch("subprocess.run", side_effect=subprocess_side_effect):
                                    with patch(
                                        "rouge.core.workflow.steps.update_pr_commits.emit_comment_from_payload",
                                        return_value=("success", "ok"),
                                    ):
                                        result = step.run(mock_context)

        # Verify execute_template was called once with compose-commits request
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        request = call_args[0][0]
        assert request.slash_command == "/adw-compose-commits"
        assert result.success is True

    def test_compose_commits_failure_stops_push(self, mock_context):
        """Test that a failed compose-commits prevents git push."""
        step = UpdatePRCommitsStep()

        mock_response = Mock(success=False, output="Error composing commits")
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"

        with patch(
            "rouge.core.workflow.steps.update_pr_commits.get_repo_path", return_value="/repo"
        ):
            with patch(
                "rouge.core.workflow.steps.update_pr_commits.make_progress_comment_handler",
                return_value=lambda x: None,
            ):
                with patch(
                    "rouge.core.workflow.steps.update_pr_commits.ClaudeAgentTemplateRequest",
                    return_value=mock_request_instance,
                ):
                    with patch(
                        "rouge.core.workflow.steps.update_pr_commits.execute_template",
                        return_value=mock_response,
                    ):
                        with patch(
                            "rouge.core.workflow.steps.update_pr_commits.emit_comment_from_payload",
                            return_value=("success", "ok"),
                        ):
                            with patch("subprocess.run") as mock_subprocess:
                                result = step.run(mock_context)

        assert result.success is False
        mock_subprocess.assert_not_called()

    def test_compose_commits_invalid_json_stops_push(self, mock_context):
        """Test that invalid JSON from compose-commits prevents git push."""
        step = UpdatePRCommitsStep()

        mock_response = Mock(success=True, output="not valid json")
        mock_parse = Mock(success=False, error="Invalid JSON", data=None)
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"

        with patch(
            "rouge.core.workflow.steps.update_pr_commits.get_repo_path", return_value="/repo"
        ):
            with patch(
                "rouge.core.workflow.steps.update_pr_commits.make_progress_comment_handler",
                return_value=lambda x: None,
            ):
                with patch(
                    "rouge.core.workflow.steps.update_pr_commits.ClaudeAgentTemplateRequest",
                    return_value=mock_request_instance,
                ):
                    with patch(
                        "rouge.core.workflow.steps.update_pr_commits.execute_template",
                        return_value=mock_response,
                    ):
                        with patch(
                            "rouge.core.workflow.steps.update_pr_commits.parse_and_validate_json",
                            return_value=mock_parse,
                        ):
                            with patch(
                                "rouge.core.workflow.steps.update_pr_commits.emit_comment_from_payload",
                                return_value=("success", "ok"),
                            ):
                                with patch("subprocess.run") as mock_subprocess:
                                    result = step.run(mock_context)

        assert result.success is False
        mock_subprocess.assert_not_called()

    def test_compose_commits_exception_stops_push(self, mock_context):
        """Test that an exception from execute_template prevents git push."""
        step = UpdatePRCommitsStep()

        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"

        with patch(
            "rouge.core.workflow.steps.update_pr_commits.get_repo_path", return_value="/repo"
        ):
            with patch(
                "rouge.core.workflow.steps.update_pr_commits.make_progress_comment_handler",
                return_value=lambda x: None,
            ):
                with patch(
                    "rouge.core.workflow.steps.update_pr_commits.ClaudeAgentTemplateRequest",
                    return_value=mock_request_instance,
                ):
                    with patch(
                        "rouge.core.workflow.steps.update_pr_commits.execute_template",
                        side_effect=RuntimeError("agent failed"),
                    ):
                        with patch(
                            "rouge.core.workflow.steps.update_pr_commits.emit_comment_from_payload",
                            return_value=("success", "ok"),
                        ):
                            with patch("subprocess.run") as mock_subprocess:
                                result = step.run(mock_context)

        assert result.success is False
        mock_subprocess.assert_not_called()


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
