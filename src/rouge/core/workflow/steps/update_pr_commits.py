"""Update PR/MR with new commits step implementation."""

import json
import logging
import os
import shutil
import subprocess
from typing import Optional, Tuple

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)


def _emit_and_log(issue_id: int, adw_id: str, text: str, raw: dict) -> None:
    """Helper to emit comment and log based on status.

    Args:
        issue_id: Issue ID
        adw_id: ADW ID
        text: Comment text
        raw: Raw payload data
    """
    payload = CommentPayload(
        issue_id=issue_id,
        adw_id=adw_id,
        text=text,
        raw=raw,
        source="system",
        kind="workflow",
    )
    status, msg = emit_comment_from_payload(payload)
    if status == "success":
        logger.debug(msg)
    elif status == "skipped":
        logger.info(msg)
    else:
        logger.error(msg)


class UpdatePRCommitsStep(WorkflowStep):
    """Push new commits to an existing pull request or merge request.

    This step is used in patch workflows to add new commits to an existing
    PR/MR. It does not create new PRs/MRs.

    Platform detection is performed via git CLI tools (``gh`` for GitHub,
    ``glab`` for GitLab) rather than loading artifacts from a parent workflow,
    allowing patch workflows to operate independently.
    """

    @property
    def name(self) -> str:
        return "Updating pull request with patch commits"

    @property
    def is_critical(self) -> bool:
        # PR update is best-effort - workflow continues on failure
        return False

    def _detect_pr_platform(self, repo_path: str) -> Tuple[Optional[str], Optional[str]]:
        """Detect the existing PR/MR platform and URL using git CLI tools.

        Tries ``gh pr view`` (GitHub) first, then ``glab mr view`` (GitLab).
        Returns the first platform that succeeds.

        Args:
            repo_path: Path to the repository root

        Returns:
            Tuple of (platform, url) where platform is "github" or "gitlab",
            or (None, None) if no PR/MR is detected or no CLI tool is available.
        """
        # Try GitHub first via gh CLI
        if shutil.which("gh"):
            github_pat = os.environ.get("GITHUB_PAT")
            env = os.environ.copy()
            if github_pat:
                env["GH_TOKEN"] = github_pat

            try:
                result = subprocess.run(
                    ["gh", "pr", "view", "--json", "url"],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30,
                    cwd=repo_path,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout.strip())
                    url = data.get("url", "")
                    if url:
                        logger.debug("Detected GitHub PR: %s", url)
                        return ("github", url)
            except (
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
                OSError,
                subprocess.SubprocessError,
            ):
                logger.debug("gh pr view failed or timed out, trying GitLab")

        # Try GitLab via glab CLI
        if shutil.which("glab"):
            gitlab_pat = os.environ.get("GITLAB_PAT")
            env = os.environ.copy()
            if gitlab_pat:
                env["GITLAB_TOKEN"] = gitlab_pat

            try:
                result = subprocess.run(
                    ["glab", "mr", "view", "--output", "json"],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=30,
                    cwd=repo_path,
                )
                if result.returncode == 0:
                    data = json.loads(result.stdout.strip())
                    url = data.get("web_url", "")
                    if url:
                        logger.debug("Detected GitLab MR: %s", url)
                        return ("gitlab", url)
            except (
                subprocess.TimeoutExpired,
                json.JSONDecodeError,
                OSError,
                subprocess.SubprocessError,
            ):
                logger.debug("glab mr view failed or timed out")

        return (None, None)

    def run(self, context: WorkflowContext) -> StepResult:
        """Push new commits to an existing PR/MR.

        Detects the PR/MR platform by running git CLI tools (``gh`` or ``glab``)
        rather than loading artifacts from a parent workflow.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        repo_path = get_repo_path()

        # Check if any CLI tool is available
        has_gh = shutil.which("gh") is not None
        has_glab = shutil.which("glab") is not None

        if not has_gh and not has_glab:
            skip_msg = (
                "PR update skipped: neither gh (GitHub) nor glab (GitLab) " "CLI found in PATH"
            )
            logger.warning(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "pr-update-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Detect platform and PR/MR URL
        platform, pr_url = self._detect_pr_platform(repo_path)

        if not platform or not pr_url:
            error_msg = "No existing PR/MR found for patch update"
            logger.warning(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)

        # Determine which PAT to use based on detected platform
        if platform == "github":
            pat = os.environ.get("GITHUB_PAT")
            pat_name = "GITHUB_PAT"
            token_env_var = "GH_TOKEN"
        else:  # gitlab
            pat = os.environ.get("GITLAB_PAT")
            pat_name = "GITLAB_PAT"
            token_env_var = "GITLAB_TOKEN"

        if not pat:
            skip_msg = f"PR update skipped: {pat_name} environment variable not set"
            logger.info(skip_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                skip_msg,
                {"output": "pr-update-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        try:
            # Execute with appropriate token environment variable
            env = os.environ.copy()
            env[token_env_var] = pat

            # Check if we're on a branch (not in detached HEAD state)
            branch_check = subprocess.run(
                ["git", "symbolic-ref", "--short", "HEAD"],
                capture_output=True,
                text=True,
                cwd=repo_path,
            )

            if branch_check.returncode != 0:
                error_msg = "Cannot push: not on a branch (detached HEAD state)"
                logger.error(error_msg)
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    error_msg,
                    {"output": "pr-update-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            branch = branch_check.stdout.strip()
            logger.debug("On branch: %s", branch)

            # Push commits to origin (the PR/MR will automatically update)
            push_cmd = ["git", "push", "origin", branch]
            logger.debug("Pushing patch commits to origin...")

            push_result = subprocess.run(
                push_cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
                cwd=repo_path,
            )

            if push_result.returncode != 0:
                error_msg = (
                    f"git push failed (exit code {push_result.returncode}): "
                    f"{push_result.stderr}"
                )
                logger.warning(error_msg)
                _emit_and_log(
                    context.require_issue_id,
                    context.adw_id,
                    error_msg,
                    {"output": "pr-update-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            logger.info("Patch commits pushed to PR/MR: %s", pr_url)

            # Emit progress comment indicating commits were added
            comment_msg = "Commits pushed to branch"
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                comment_msg,
                {
                    "output": "pr-updated",
                    "url": pr_url,
                    "platform": platform,
                },
            )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "git push timed out after 60 seconds"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except (OSError, PermissionError, ValueError, subprocess.SubprocessError) as e:
            error_msg = f"Error updating PR/MR with patch commits: {e}"
            logger.exception(error_msg)
            _emit_and_log(
                context.require_issue_id,
                context.adw_id,
                error_msg,
                {"output": "pr-update-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception:
            # Re-raise unexpected exceptions after logging
            logger.exception("Unexpected error updating PR/MR")
            raise
