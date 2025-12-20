"""Create GitHub pull request step implementation."""

import logging
import os
import shutil
import subprocess

from rouge.core.workflow.shared import get_repo_path
from rouge.core.workflow.step_base import WorkflowContext, WorkflowStep
from rouge.core.workflow.types import StepResult
from rouge.core.workflow.workflow_io import emit_progress_comment

logger = logging.getLogger(__name__)


class CreateGitHubPullRequestStep(WorkflowStep):
    """Create GitHub pull request via gh CLI."""

    @property
    def name(self) -> str:
        return "Creating GitHub pull request"

    @property
    def is_critical(self) -> bool:
        # PR creation is best-effort - workflow continues on failure
        return False

    def run(self, context: WorkflowContext) -> StepResult:
        """Create GitHub pull request using gh CLI.

        Args:
            context: Workflow context

        Returns:
            StepResult with success status and optional error message
        """
        # Check for pr_details in context
        pr_details = context.data.get("pr_details")
        if not pr_details:
            skip_msg = "PR creation skipped: no PR details in context"
            logger.info(skip_msg)
            emit_progress_comment(
                context.issue_id,
                skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        title = pr_details.get("title", "")
        summary = pr_details.get("summary", "")
        commits = pr_details.get("commits", [])

        if not title:
            skip_msg = "PR creation skipped: PR title is empty"
            logger.info(skip_msg)
            emit_progress_comment(
                context.issue_id,
                skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Check for GITHUB_PAT environment variable
        github_pat = os.environ.get("GITHUB_PAT")
        if not github_pat:
            skip_msg = "PR creation skipped: GITHUB_PAT environment variable not set"
            logger.info(skip_msg)
            emit_progress_comment(
                context.issue_id,
                skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        # Proactively check for gh CLI availability
        if not shutil.which("gh"):
            skip_msg = "PR creation skipped: gh CLI not found in PATH"
            logger.info(skip_msg)
            logger.debug("Current PATH: %s", os.environ.get("PATH", ""))
            emit_progress_comment(
                context.issue_id,
                skip_msg,
                raw={"output": "pull-request-skipped", "reason": skip_msg},
            )
            return StepResult.ok(None)

        try:
            # Execute with GH_TOKEN environment variable
            env = os.environ.copy()
            env["GH_TOKEN"] = github_pat

            repo_path = get_repo_path()

            # Push branch to origin before creating PR
            push_cmd = ["git", "push", "--set-upstream", "origin", "HEAD"]
            logger.debug("Pushing current branch to origin...")
            try:
                push_result = subprocess.run(
                    push_cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=60,
                    cwd=repo_path,
                )
                if push_result.returncode == 0:
                    logger.debug("Branch pushed successfully")
                else:
                    logger.debug(
                        "git push failed (exit code %d): %s",
                        push_result.returncode,
                        push_result.stderr,
                    )
            except subprocess.TimeoutExpired:
                logger.debug("git push timed out, continuing to PR creation")
            except Exception as e:
                logger.debug("git push failed: %s", e)

            # Build gh pr create command
            cmd = [
                "gh",
                "pr",
                "create",
                "--title",
                title,
                "--body",
                summary,
            ]

            logger.debug("Executing: %s (cwd=%s)", " ".join(cmd), repo_path)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=120,
                cwd=repo_path,
            )

            if result.returncode != 0:
                error_msg = f"gh pr create failed (exit code {result.returncode}): {result.stderr}"
                logger.warning(
                    "gh pr create failed (exit code %d): %s",
                    result.returncode,
                    result.stderr,
                )
                emit_progress_comment(
                    context.issue_id,
                    error_msg,
                    raw={"output": "pull-request-failed", "error": error_msg},
                )
                return StepResult.fail(error_msg)

            # Parse PR URL from output (gh pr create outputs the URL)
            pr_url = result.stdout.strip()
            logger.info("Pull request created: %s", pr_url)

            # Emit progress comment with PR details
            comment_data = {
                "commits": commits,
                "output": "pull-request-created",
                "url": pr_url,
            }
            emit_progress_comment(
                context.issue_id,
                f"Pull request created: {pr_url}",
                raw=comment_data,
            )

            return StepResult.ok(None)

        except subprocess.TimeoutExpired:
            error_msg = "gh pr create timed out after 120 seconds"
            logger.warning(error_msg)
            emit_progress_comment(
                context.issue_id,
                error_msg,
                raw={"output": "pull-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except FileNotFoundError:
            error_msg = "gh CLI not found, skipping PR creation"
            logger.warning(error_msg)
            emit_progress_comment(
                context.issue_id,
                error_msg,
                raw={"output": "pull-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
        except Exception as e:
            error_msg = f"Error creating pull request: {e}"
            logger.warning(error_msg)
            emit_progress_comment(
                context.issue_id,
                error_msg,
                raw={"output": "pull-request-failed", "error": error_msg},
            )
            return StepResult.fail(error_msg)
