"""Update PR/MR with new commits step implementation."""

import logging
import os
import subprocess

from rouge.core.models import CommentPayload
from rouge.core.notifications.comments import emit_comment_from_payload
from rouge.core.workflow.artifacts import PullRequestArtifact
from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult

logger = logging.getLogger(__name__)


class UpdatePRCommitsStep(WorkflowStep):
    """Push new commits to an existing pull request or merge request.

    This step is used in patch workflows to add new commits to an existing
    PR/MR from the parent workflow. It does not create new PRs/MRs.
    """

    @property
    def name(self) -> str:
        return "Updating pull request with patch commits"

    @property
    def is_critical(self) -> bool:
        # PR update is best-effort - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Push new commits to an existing PR/MR.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        # Try to load pull_request from artifact (from parent workflow)
        pull_request = context.load_artifact_if_missing(
            "pull_request",
            "pull_request",
            PullRequestArtifact,
            lambda a: {"url": a.url, "platform": a.platform},
        )

        if not pull_request:
            error_msg = "No existing PR/MR found for patch update"
            logger.warning(error_msg)
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pr-update-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)

        pr_url = pull_request.get("url", "")
        platform = pull_request.get("platform", "")

        if not pr_url:
            error_msg = "PR/MR URL is empty in artifact"
            logger.warning(error_msg)
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pr-update-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)

        # Determine which PAT to use based on platform
        if platform == "github":
            pat = os.environ.get("GITHUB_PAT")
            pat_name = "GITHUB_PAT"
            token_env_var = "GH_TOKEN"
        elif platform == "gitlab":
            pat = os.environ.get("GITLAB_PAT")
            pat_name = "GITLAB_PAT"
            token_env_var = "GITLAB_TOKEN"
        else:
            error_msg = f"Unknown platform: {platform}"
            logger.warning(error_msg)
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pr-update-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)

        if not pat:
            skip_msg = f"PR update skipped: {pat_name} environment variable not set"
            logger.info(skip_msg)
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text=skip_msg,
                raw={"output": "pr-update-skipped", "reason": skip_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.ok(None)

        try:
            # Execute with appropriate token environment variable
            env = os.environ.copy()
            env[token_env_var] = pat

            repo_path = get_repo_path()

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
                payload = CommentPayload(
                    issue_id=context.issue_id,
                    adw_id=context.adw_id,
                    text=error_msg,
                    raw={"output": "pr-update-failed", "error": error_msg},
                    source="system",
                    kind="workflow",
                )
                status, msg = emit_comment_from_payload(payload)
                if status == "success":
                    logger.debug(msg)
                else:
                    logger.error(msg)
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
                    f"git push failed (exit code {push_result.returncode}): {push_result.stderr}"
                )
                logger.warning(error_msg)
                payload = CommentPayload(
                    issue_id=context.issue_id,
                    adw_id=context.adw_id,
                    text=error_msg,
                    raw={"output": "pr-update-failed", "error": error_msg},
                    source="system",
                    kind="workflow",
                )
                status, msg = emit_comment_from_payload(payload)
                if status == "success":
                    logger.debug(msg)
                else:
                    logger.error(msg)
                return StepResult.fail(error_msg)

            logger.info("Patch commits pushed to PR/MR: %s", pr_url)

            # Emit progress comment indicating commits were added
            platform_name = "Pull request" if platform == "github" else "Merge request"
            comment_msg = f"{platform_name} updated with patch commits: {pr_url}"
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text=comment_msg,
                raw={
                    "output": "pr-updated",
                    "url": pr_url,
                    "platform": platform,
                },
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "git push timed out after 60 seconds"
            logger.warning(error_msg)
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pr-update-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)
        except (OSError, PermissionError, ValueError, subprocess.SubprocessError) as e:
            error_msg = f"Error updating PR/MR with patch commits: {e}"
            logger.warning(error_msg)
            payload = CommentPayload(
                issue_id=context.issue_id,
                adw_id=context.adw_id,
                text=error_msg,
                raw={"output": "pr-update-failed", "error": error_msg},
                source="system",
                kind="workflow",
            )
            status, msg = emit_comment_from_payload(payload)
            if status == "success":
                logger.debug(msg)
            else:
                logger.error(msg)
            return StepResult.fail(error_msg)
        except Exception:
            # Re-raise unexpected exceptions after logging
            logger.exception("Unexpected error updating PR/MR")
            raise
