"""Tests for ComposeCommitsStep workflow step.

Tests focus on platform selection via DEV_SEC_OPS_PLATFORM and git CLI detection,
verifying that the step works independently without loading parent artifacts.
"""

import json
import subprocess
from unittest.mock import Mock, patch

import pytest

from rouge.core.workflow.step_base import WorkflowContext
from rouge.core.workflow.steps.compose_commits_step import ComposeCommitsStep


@pytest.fixture
def mock_context() -> Mock:
    """Create a mock workflow context."""
    context = Mock(spec=WorkflowContext)
    context.issue_id = 10
    context.require_issue_id = 10
    context.adw_id = "test-adw-pr-update"
    context.data = {}
    context.artifacts_enabled = True
    context.artifact_store = Mock()
    context.repo_paths = ["/repo"]
    return context


class TestDetectPrPlatform:
    """Tests for _detect_pr_platform via DEV_SEC_OPS_PLATFORM."""

    @patch("subprocess.run")
    def test_detects_github_pr_via_gh(self, mock_run, monkeypatch) -> None:
        """Test detection of GitHub PR using gh CLI."""
        step = ComposeCommitsStep()
        gh_output = json.dumps({"url": "https://github.com/org/repo/pull/42"})
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = gh_output
        mock_run.return_value = mock_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform == "github"
        assert url == "https://github.com/org/repo/pull/42"
        # Verify gh was called with correct args
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gh", "pr", "view", "--json", "url"]

    @patch("subprocess.run")
    def test_detects_gitlab_mr_via_glab(self, mock_run, monkeypatch) -> None:
        """Test detection of GitLab MR using glab CLI."""
        step = ComposeCommitsStep()
        glab_output = json.dumps({"web_url": "https://gitlab.com/org/repo/-/merge_requests/7"})
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = glab_output
        mock_run.return_value = mock_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform == "gitlab"
        assert url == "https://gitlab.com/org/repo/-/merge_requests/7"
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["glab", "mr", "view", "--output", "json"]

    @patch("subprocess.run")
    def test_returns_none_when_env_missing(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None) when DEV_SEC_OPS_PLATFORM is unset."""
        step = ComposeCommitsStep()

        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_returns_none_when_env_invalid(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None) when DEV_SEC_OPS_PLATFORM is invalid."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "bitbucket")
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_returns_none_when_cli_missing(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None) when CLI is missing."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        mock_run.side_effect = FileNotFoundError
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None

    @patch("subprocess.run")
    def test_returns_none_when_github_cli_fails(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None) when the selected CLI command fails."""
        step = ComposeCommitsStep()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stdout = ""
        mock_run.return_value = fail_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None

    @patch("subprocess.run")
    def test_handles_gh_timeout(self, mock_run, monkeypatch) -> None:
        """Test handles timeout from gh command gracefully."""
        step = ComposeCommitsStep()

        def raise_timeout(*_args, **_kwargs):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        mock_run.side_effect = raise_timeout
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None

    @patch("subprocess.run")
    def test_handles_invalid_json_from_gh(self, mock_run, monkeypatch) -> None:
        """Test handles invalid JSON output from gh gracefully."""
        step = ComposeCommitsStep()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_run.return_value = mock_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        platform, url = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None


class TestRunWhenPlatformMissing:
    """Tests for ComposeCommitsStep.run when platform cannot be detected."""

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_fails_when_env_missing(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """Test step fails when DEV_SEC_OPS_PLATFORM is not set."""
        step = ComposeCommitsStep()

        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)

        # Mock compose-commits dependencies (runs before platform detection)
        mock_response = Mock(success=True, output='{"output": "commits-composed"}')
        parse_result = Mock(success=True, data={"output": "commits-composed"}, error=None)
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response
        mock_parse.return_value = parse_result

        result = step.run(mock_context)

        assert result.success is False


class TestComposeCommits:
    """Tests for compose-commits integration in ComposeCommitsStep.run."""

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_compose_commits_called_before_push(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """Test that execute_template is called with /adw-compose-commits before push."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        mock_response = Mock(
            success=True,
            output='{"output": "compose-commits", "summary": "Test commits", "commits": []}',
        )
        mock_parse_response = Mock(
            success=True,
            data={"output": "compose-commits", "summary": "Test commits", "commits": []},
            error=None,
        )

        # Mock ClaudeAgentTemplateRequest to bypass Pydantic slash_command validation
        mock_request_instance = Mock(
            slash_command="/adw-compose-commits",
            agent_name="commit_composer",
        )
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response
        mock_parse.return_value = mock_parse_response

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

        mock_subprocess.side_effect = subprocess_side_effect
        result = step.run(mock_context)

        # Verify execute_template was called once with compose-commits request
        mock_exec.assert_called_once()
        call_args = mock_exec.call_args
        request = call_args[0][0]
        assert request.slash_command == "/adw-compose-commits"
        assert mock_request.call_args.kwargs["json_schema"] is not None
        assert '"const": "compose-commits"' in mock_request.call_args.kwargs["json_schema"]
        assert result.success is True

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_compose_commits_failure_stops_push(
        self,
        mock_request,
        mock_exec,
        mock_subprocess,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """Test that a failed compose-commits prevents git push."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        mock_response = Mock(success=False, output="Error composing commits")
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response

        result = step.run(mock_context)

        assert result.success is False
        mock_subprocess.assert_not_called()

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_compose_commits_invalid_json_stops_push(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """Test that invalid JSON from compose-commits prevents git push."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        mock_response = Mock(success=True, output="not valid json")
        mock_parse_result = Mock(success=False, error="Invalid JSON", data=None)
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response
        mock_parse.return_value = mock_parse_result

        result = step.run(mock_context)

        assert result.success is False
        mock_subprocess.assert_not_called()

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_compose_commits_exception_stops_push(
        self,
        mock_request,
        mock_exec,
        mock_subprocess,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """Test that an exception from execute_template prevents git push."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.side_effect = RuntimeError("agent failed")

        result = step.run(mock_context)

        assert result.success is False
        mock_subprocess.assert_not_called()


class TestComposeCommitsMultiRepo:
    """Tests for ComposeCommitsStep multi-repo push behavior."""

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_compose_commits_multi_repo_push(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """Two repos, both have PRs — verify push runs for each."""
        step = ComposeCommitsStep()
        mock_context.repo_paths = ["/repo/a", "/repo/b"]

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        mock_response = Mock(
            success=True,
            output='{"output": "compose-commits", "summary": "Test", "commits": []}',
        )
        mock_parse_response = Mock(
            success=True,
            data={"output": "compose-commits", "summary": "Test", "commits": []},
            error=None,
        )
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response
        mock_parse.return_value = mock_parse_response

        def subprocess_side_effect(cmd, **kwargs):
            cwd = kwargs.get("cwd", "")
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return Mock(returncode=0, stdout="feature-branch\n", stderr="")
            if cmd[0] == "git" and cmd[1] == "push":
                return Mock(returncode=0, stdout="", stderr="")
            # gh pr view for platform detection
            return Mock(
                returncode=0,
                stdout=json.dumps({"url": f"https://github.com/org/repo/pull/1"}),
            )

        mock_subprocess.side_effect = subprocess_side_effect

        result = step.run(mock_context)

        assert result.success is True

        # Count push calls (git push origin feature-branch) — should be 2
        push_calls = [
            call
            for call in mock_subprocess.call_args_list
            if len(call[0]) > 0
            and len(call[0][0]) >= 2
            and call[0][0][0] == "git"
            and call[0][0][1] == "push"
        ]
        assert len(push_calls) == 2

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_compose_commits_multi_repo_partial_pr(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """One repo has PR, other doesn't — verify push runs only for the repo with a PR."""
        step = ComposeCommitsStep()
        mock_context.repo_paths = ["/repo/with-pr", "/repo/no-pr"]

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        mock_response = Mock(
            success=True,
            output='{"output": "compose-commits", "summary": "Test", "commits": []}',
        )
        mock_parse_response = Mock(
            success=True,
            data={"output": "compose-commits", "summary": "Test", "commits": []},
            error=None,
        )
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response
        mock_parse.return_value = mock_parse_response

        def subprocess_side_effect(cmd, **kwargs):
            cwd = kwargs.get("cwd", "")
            if cmd == ["gh", "pr", "view", "--json", "url"]:
                # Only /repo/with-pr has a PR
                if cwd == "/repo/with-pr":
                    return Mock(
                        returncode=0,
                        stdout=json.dumps({"url": "https://github.com/org/repo/pull/1"}),
                    )
                else:
                    return Mock(returncode=1, stdout="", stderr="no PR found")
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return Mock(returncode=0, stdout="feature-branch\n", stderr="")
            if cmd[0] == "git" and cmd[1] == "push":
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=1, stdout="", stderr="")

        mock_subprocess.side_effect = subprocess_side_effect

        result = step.run(mock_context)

        # Step succeeds because at least one repo pushed
        assert result.success is True

        # Count push calls — should be 1 (only the repo with a PR)
        push_calls = [
            call
            for call in mock_subprocess.call_args_list
            if len(call[0]) > 0
            and len(call[0][0]) >= 2
            and call[0][0][0] == "git"
            and call[0][0][1] == "push"
        ]
        assert len(push_calls) == 1


class TestUpdatePRCommitsStepProperties:
    """Tests for ComposeCommitsStep properties."""

    def test_step_name(self) -> None:
        """Test step has correct name."""
        step = ComposeCommitsStep()
        assert step.name == "Updating pull request with patch commits"

    def test_step_is_not_critical(self) -> None:
        """Test step is not critical."""
        step = ComposeCommitsStep()
        assert step.is_critical is False
