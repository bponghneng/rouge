"""Tests for ComposeCommitsStep workflow step.

Tests focus on platform selection via DEV_SEC_OPS_PLATFORM and git CLI detection,
verifying that the step works independently without loading parent artifacts.
"""

import json
import subprocess
from typing import Any, Callable, Sequence
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
    # Return None from load_optional_artifact so get_affected_repo_paths
    # falls back to context.repo_paths (the default, non-implement path).
    context.load_optional_artifact.return_value = None
    return context


class TestDetectPrPlatform:
    """Tests for _detect_pr_platform via DEV_SEC_OPS_PLATFORM."""

    @patch("subprocess.run")
    def test_detects_github_pr_via_gh(self, mock_run, monkeypatch) -> None:
        """Test detection of GitHub PR using gh CLI."""
        step = ComposeCommitsStep()
        gh_output = json.dumps({"url": "https://github.com/org/repo/pull/42", "number": 42})
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = gh_output
        mock_run.return_value = mock_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform == "github"
        assert url == "https://github.com/org/repo/pull/42"
        assert number == 42
        # Verify gh was called with correct args
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["gh", "pr", "view", "--json", "url,number"]

    @patch("subprocess.run")
    def test_detects_gitlab_mr_via_glab(self, mock_run, monkeypatch) -> None:
        """Test detection of GitLab MR using glab CLI."""
        step = ComposeCommitsStep()
        glab_output = json.dumps(
            {"web_url": "https://gitlab.com/org/repo/-/merge_requests/7", "iid": 7}
        )
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = glab_output
        mock_run.return_value = mock_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform == "gitlab"
        assert url == "https://gitlab.com/org/repo/-/merge_requests/7"
        assert number == 7
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd == ["glab", "mr", "view", "--output", "json"]

    @patch("subprocess.run")
    def test_returns_none_when_env_missing(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None, None) when DEV_SEC_OPS_PLATFORM is unset."""
        step = ComposeCommitsStep()

        monkeypatch.delenv("DEV_SEC_OPS_PLATFORM", raising=False)
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        assert number is None
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_returns_none_when_env_invalid(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None, None) when DEV_SEC_OPS_PLATFORM is invalid."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "bitbucket")
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        assert number is None
        mock_run.assert_not_called()

    @patch("subprocess.run")
    def test_returns_none_when_cli_missing(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None, None) when CLI is missing."""
        step = ComposeCommitsStep()

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        mock_run.side_effect = FileNotFoundError
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        assert number is None

    @patch("subprocess.run")
    def test_returns_none_when_github_cli_fails(self, mock_run, monkeypatch) -> None:
        """Test returns (None, None, None) when the selected CLI command fails."""
        step = ComposeCommitsStep()

        fail_result = Mock()
        fail_result.returncode = 1
        fail_result.stdout = ""
        mock_run.return_value = fail_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        assert number is None

    @patch("subprocess.run")
    def test_handles_gh_timeout(self, mock_run, monkeypatch) -> None:
        """Test handles timeout from gh command gracefully."""
        step = ComposeCommitsStep()

        def raise_timeout(*_args: Any, **_kwargs: Any) -> None:
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        mock_run.side_effect = raise_timeout
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        assert number is None

    @patch("subprocess.run")
    def test_handles_invalid_json_from_gh(self, mock_run, monkeypatch) -> None:
        """Test handles invalid JSON output from gh gracefully."""
        step = ComposeCommitsStep()

        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_run.return_value = mock_result

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        platform, url, number = step._detect_pr_platform("/fake/repo", "test-adw-id")

        assert platform is None
        assert url is None
        assert number is None


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
            output=(
                '{"output": "compose-commits", "repos": ['
                '{"repo": "/repo", "summary": "Test commits", "commits": []}'
                "]}"
            ),
        )
        mock_parse_response = Mock(
            success=True,
            data={
                "output": "compose-commits",
                "repos": [{"repo": "/repo", "summary": "Test commits", "commits": []}],
            },
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

        def subprocess_side_effect(cmd: Sequence[str], **_kwargs: Any) -> Mock:
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return branch_result
            if cmd[0] == "git" and cmd[1] == "push":
                return push_result
            # gh pr view for platform detection
            return Mock(
                returncode=0,
                stdout=json.dumps({"url": "https://github.com/org/repo/pull/1", "number": 1}),
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
            output=(
                '{"output": "compose-commits", "repos": ['
                '{"repo": "/repo", "summary": "Test", "commits": []}'
                "]}"
            ),
        )
        mock_parse_response = Mock(
            success=True,
            data={
                "output": "compose-commits",
                "repos": [{"repo": "/repo", "summary": "Test", "commits": []}],
            },
            error=None,
        )
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response
        mock_parse.return_value = mock_parse_response

        def subprocess_side_effect(cmd: Sequence[str], **kwargs: Any) -> Mock:
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return Mock(returncode=0, stdout="feature-branch\n", stderr="")
            if cmd[0] == "git" and cmd[1] == "push":
                return Mock(returncode=0, stdout="", stderr="")
            # gh pr view for platform detection
            return Mock(
                returncode=0,
                stdout=json.dumps({"url": "https://github.com/org/repo/pull/1", "number": 1}),
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
            output=(
                '{"output": "compose-commits", "repos": ['
                '{"repo": "/repo", "summary": "Test", "commits": []}'
                "]}"
            ),
        )
        mock_parse_response = Mock(
            success=True,
            data={
                "output": "compose-commits",
                "repos": [{"repo": "/repo", "summary": "Test", "commits": []}],
            },
            error=None,
        )
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance
        mock_exec.return_value = mock_response
        mock_parse.return_value = mock_parse_response

        def subprocess_side_effect(cmd: Sequence[str], **kwargs: Any) -> Mock:
            cwd = kwargs.get("cwd", "")
            if cmd == ["gh", "pr", "view", "--json", "url,number"]:
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


class TestPatchReviewContext:
    """Tests for review-context posting after successful push."""

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _mock_compose_commits(mock_request: Mock, mock_exec: Mock, mock_parse: Mock) -> None:
        """Wire up mocks so compose-commits succeeds."""
        mock_request_instance = Mock()
        mock_request_instance.model_dump_json.return_value = "{}"
        mock_request.return_value = mock_request_instance

        mock_exec.return_value = Mock(
            success=True,
            output=(
                '{"output": "compose-commits", "repos": ['
                '{"repo": "/repo", "summary": "s", "commits": []}'
                "]}"
            ),
        )
        mock_parse.return_value = Mock(
            success=True,
            data={
                "output": "compose-commits",
                "repos": [{"repo": "/repo", "summary": "s", "commits": []}],
            },
            error=None,
        )

    @staticmethod
    def _subprocess_github(pr_number: int = 42) -> Callable[..., Mock]:
        """Return a subprocess side-effect for a GitHub repo with a PR."""

        def _side_effect(cmd: Sequence[str], **kwargs: Any) -> Mock:
            if cmd == ["gh", "pr", "view", "--json", "url,number"]:
                return Mock(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "url": "https://github.com/org/repo/pull/%d" % pr_number,
                            "number": pr_number,
                        }
                    ),
                )
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return Mock(returncode=0, stdout="feature-branch\n", stderr="")
            if cmd[0] == "git" and cmd[1] == "push":
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=1, stdout="", stderr="")

        return _side_effect

    @staticmethod
    def _subprocess_gitlab(mr_number: int = 7) -> Callable[..., Mock]:
        """Return a subprocess side-effect for a GitLab repo with an MR."""

        def _side_effect(cmd: Sequence[str], **kwargs: Any) -> Mock:
            if cmd == ["glab", "mr", "view", "--output", "json"]:
                return Mock(
                    returncode=0,
                    stdout=json.dumps(
                        {
                            "web_url": (
                                "https://gitlab.com/org/repo/-/merge_requests/%d" % mr_number
                            ),
                            "iid": mr_number,
                        }
                    ),
                )
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return Mock(returncode=0, stdout="feature-branch\n", stderr="")
            if cmd[0] == "git" and cmd[1] == "push":
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=1, stdout="", stderr="")

        return _side_effect

    # -- tests ------------------------------------------------------------

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("rouge.core.workflow.steps.compose_commits_step.post_gh_attachment_comment")
    @patch("rouge.core.workflow.steps.compose_commits_step.load_and_render_patch_attachment")
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_review_context_posted_after_push_github(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        mock_load_attachment,
        mock_post_gh,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """After a successful push on GitHub, post_gh_attachment_comment is called."""
        self._mock_compose_commits(mock_request, mock_exec, mock_parse)
        mock_load_attachment.return_value = "## Review Context\nSome markdown"
        mock_subprocess.side_effect = self._subprocess_github(pr_number=42)

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        step = ComposeCommitsStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_post_gh.assert_called_once()
        call_args = mock_post_gh.call_args
        assert call_args[0][0] == "/repo"  # repo_path
        assert call_args[0][1] == 42  # pr_number
        assert call_args[0][2] == "## Review Context\nSome markdown"  # body
        # Fourth arg is the env dict containing GH_TOKEN
        assert call_args[0][3]["GH_TOKEN"] == "fake-token"

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("rouge.core.workflow.steps.compose_commits_step.post_glab_attachment_note")
    @patch("rouge.core.workflow.steps.compose_commits_step.load_and_render_patch_attachment")
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_review_context_posted_after_push_gitlab(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        mock_load_attachment,
        mock_post_glab,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """After a successful push on GitLab, post_glab_attachment_note is called."""
        self._mock_compose_commits(mock_request, mock_exec, mock_parse)
        mock_load_attachment.return_value = "## Review Context\nGitLab markdown"
        mock_subprocess.side_effect = self._subprocess_gitlab(mr_number=7)

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "gitlab")
        monkeypatch.setenv("GITLAB_PAT", "fake-token")

        step = ComposeCommitsStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_post_glab.assert_called_once()
        call_args = mock_post_glab.call_args
        assert call_args[0][0] == "/repo"  # repo_path
        assert call_args[0][1] == 7  # mr number (iid)
        assert call_args[0][2] == "## Review Context\nGitLab markdown"  # body
        assert call_args[0][3]["GITLAB_TOKEN"] == "fake-token"

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("rouge.core.workflow.steps.compose_commits_step.post_gh_attachment_comment")
    @patch("rouge.core.workflow.steps.compose_commits_step.load_and_render_patch_attachment")
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_review_context_failure_does_not_fail_step(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        mock_load_attachment,
        mock_post_gh,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """If post_gh_attachment_comment raises OSError, the step still succeeds."""
        self._mock_compose_commits(mock_request, mock_exec, mock_parse)
        mock_load_attachment.return_value = "## Review Context"
        mock_post_gh.side_effect = OSError("network error")
        mock_subprocess.side_effect = self._subprocess_github(pr_number=42)

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        step = ComposeCommitsStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_post_gh.assert_called_once()

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("rouge.core.workflow.steps.compose_commits_step.post_gh_attachment_comment")
    @patch("rouge.core.workflow.steps.compose_commits_step.post_glab_attachment_note")
    @patch("rouge.core.workflow.steps.compose_commits_step.load_and_render_patch_attachment")
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_review_context_skipped_when_no_attachment(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        mock_load_attachment,
        mock_post_glab,
        mock_post_gh,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """When load_and_render_patch_attachment returns None, posting is skipped."""
        self._mock_compose_commits(mock_request, mock_exec, mock_parse)
        mock_load_attachment.return_value = None
        mock_subprocess.side_effect = self._subprocess_github(pr_number=42)

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        step = ComposeCommitsStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_post_gh.assert_not_called()
        mock_post_glab.assert_not_called()

    @patch(
        "rouge.core.workflow.step_utils.emit_comment_from_payload",
        return_value=("success", "ok"),
    )
    @patch("rouge.core.workflow.steps.compose_commits_step.post_gh_attachment_comment")
    @patch("rouge.core.workflow.steps.compose_commits_step.post_glab_attachment_note")
    @patch("rouge.core.workflow.steps.compose_commits_step.load_and_render_patch_attachment")
    @patch("subprocess.run")
    @patch("rouge.core.workflow.steps.compose_commits_step.parse_and_validate_json")
    @patch("rouge.core.workflow.steps.compose_commits_step.execute_template")
    @patch("rouge.core.workflow.steps.compose_commits_step.ClaudeAgentTemplateRequest")
    def test_review_context_skipped_when_no_pr_number(
        self,
        mock_request,
        mock_exec,
        mock_parse,
        mock_subprocess,
        mock_load_attachment,
        mock_post_glab,
        mock_post_gh,
        _mock_emit,
        monkeypatch,
        mock_context,
    ) -> None:
        """When _detect_pr_platform returns no pr_number, posting is skipped."""
        self._mock_compose_commits(mock_request, mock_exec, mock_parse)
        mock_load_attachment.return_value = "## Review Context"

        # gh pr view returns url but no number field
        def _side_effect(cmd: Sequence[str], **kwargs: Any) -> Mock:
            if cmd == ["gh", "pr", "view", "--json", "url,number"]:
                return Mock(
                    returncode=0,
                    stdout=json.dumps({"url": "https://github.com/org/repo/pull/99"}),
                )
            if cmd == ["git", "symbolic-ref", "--short", "HEAD"]:
                return Mock(returncode=0, stdout="feature-branch\n", stderr="")
            if cmd[0] == "git" and cmd[1] == "push":
                return Mock(returncode=0, stdout="", stderr="")
            return Mock(returncode=1, stdout="", stderr="")

        mock_subprocess.side_effect = _side_effect

        monkeypatch.setenv("DEV_SEC_OPS_PLATFORM", "github")
        monkeypatch.setenv("GITHUB_PAT", "fake-token")

        step = ComposeCommitsStep()
        result = step.run(mock_context)

        assert result.success is True
        mock_post_gh.assert_not_called()
        mock_post_glab.assert_not_called()
